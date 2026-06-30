from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from src.core.exceptions import BrowserActionError, BrowserPageNotReadyError
from src.core.logging_utils import AgentLogger
from src.core.settings import AgentSettings

BOSS_PAGE_TEXTS = ["\u641c\u7d22", "\u804c\u4f4d", "\u767b\u5f55", "BOSS\u76f4\u8058"]


@dataclass
class BrowserPage:
    page_id: str
    title: str = ""
    url: str = ""


class BrowserMCPClient:
    def __init__(self, settings: AgentSettings, agent_logger: AgentLogger):
        self.settings = settings
        self.agent_logger = agent_logger
        self.server_params = StdioServerParameters(command=settings.mcp_command, args=settings.mcp_args)
        self._stdio_cm = None
        self._session_cm = None
        self._session: ClientSession | None = None
        self.selected_page: BrowserPage | None = None

    async def start(self) -> None:
        self._stdio_cm = stdio_client(self.server_params)
        read_stream, write_stream = await self._stdio_cm.__aenter__()
        self._session_cm = ClientSession(read_stream, write_stream)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()
        logger.info("browser client ready mode=browser_mcp_text_only command={}", self.settings.mcp_command_display)

    async def close(self) -> None:
        if self._session_cm is not None:
            await self._session_cm.__aexit__(None, None, None)
            self._session_cm = None
        if self._stdio_cm is not None:
            await self._stdio_cm.__aexit__(None, None, None)
            self._stdio_cm = None

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._session is None:
            raise BrowserActionError("Browser MCP session has not been started")
        arguments = arguments or {}
        last_error: Exception | None = None
        for attempt in range(1, 3):
            started_at = time.time()
            try:
                result = await asyncio.wait_for(
                    self._session.call_tool(tool_name, arguments=arguments),
                    timeout=self.settings.action_timeout_ms / 1000,
                )
                payload = {
                    "ok": True,
                    "tool": tool_name,
                    "arguments": arguments,
                    "result": _result_to_dict(result),
                    "attempt": attempt,
                    "duration_ms": int((time.time() - started_at) * 1000),
                }
                if self.settings.debug_dump:
                    self.agent_logger.write_mcp_event(payload)
                return payload
            except Exception as exc:
                last_error = exc
                error_payload = {
                    "ok": False,
                    "tool": tool_name,
                    "arguments": arguments,
                    "error": repr(exc),
                    "attempt": attempt,
                    "duration_ms": int((time.time() - started_at) * 1000),
                }
                self.agent_logger.write_mcp_event(error_payload)
                logger.warning("mcp tool failed tool={} attempt={} error={}", tool_name, attempt, exc)
                await asyncio.sleep(min(1.0 * attempt, 2.0))
        raise BrowserActionError(f"MCP tool {tool_name} failed: {last_error}")

    async def list_pages(self) -> list[BrowserPage]:
        payload = await self.call_tool("list_pages", {})
        pages = []
        for item in _as_list(payload["result"]):
            page_id = str(item.get("id") or item.get("pageId") or item.get("targetId") or "")
            if not page_id:
                continue
            pages.append(BrowserPage(page_id=page_id, title=str(item.get("title") or ""), url=str(item.get("url") or "")))
        return pages

    async def select_page(self, page_id: str) -> BrowserPage:
        payload = await self.call_tool("select_page", {"pageId": page_id})
        page = _page_from_payload(payload["result"], page_id)
        self.selected_page = page
        return page

    async def navigate_page(self, url: str) -> dict[str, Any]:
        return await self.call_tool("navigate_page", {"url": url})

    async def new_page(self, url: str) -> BrowserPage:
        payload = await self.call_tool("new_page", {"url": url})
        page = _page_from_payload(payload["result"])
        self.selected_page = page
        return page

    async def take_snapshot(self, verbose: bool = False) -> str:
        payload = await self.call_tool("take_snapshot", {"verbose": verbose})
        snapshot = _extract_text(payload["result"])
        if self.settings.debug_dump:
            self.agent_logger.write_debug_text("latest_snapshot.txt", snapshot)
        return snapshot

    async def click(self, uid: str) -> dict[str, Any]:
        return await self.call_tool("click", {"uid": uid})

    async def fill(self, uid: str, value: str) -> dict[str, Any]:
        return await self.call_tool("fill", {"uid": uid, "value": value})

    async def press_key(self, key: str) -> dict[str, Any]:
        return await self.call_tool("press_key", {"key": key})

    async def evaluate_script(self, script: str) -> dict[str, Any]:
        return await self.call_tool("evaluate_script", {"script": script})

    async def list_console_messages(self) -> list[dict[str, Any]]:
        payload = await self.call_tool("list_console_messages", {})
        result = _as_list(payload["result"])
        if self.settings.debug_dump:
            self.agent_logger.write_debug_json("latest_console.json", result)
        return result

    async def list_network_requests(self) -> list[dict[str, Any]]:
        payload = await self.call_tool("list_network_requests", {})
        result = _as_list(payload["result"])
        if self.settings.debug_dump:
            self.agent_logger.write_debug_json("latest_network.json", result)
        return result

    async def wait_for_text(self, texts: list[str], timeout_ms: int) -> bool:
        deadline = time.time() + timeout_ms / 1000
        targets = [text for text in texts if text]
        while time.time() < deadline:
            snapshot = await self.take_snapshot(verbose=self.settings.snapshot_verbose)
            if any(text in snapshot for text in targets):
                return True
            await asyncio.sleep(0.8)
        return False

    async def ensure_boss_page(self) -> BrowserPage:
        failures = 0
        last_pages: list[BrowserPage] = []
        for _ in range(2):
            pages = await self.list_pages()
            last_pages = pages
            if self.settings.debug_dump:
                self.agent_logger.write_debug_json("latest_pages.json", [page.__dict__ for page in pages])

            preferred = _pick_boss_page(pages)
            if preferred:
                await self.select_page(preferred.page_id)
                snapshot = await self.take_snapshot(verbose=self.settings.snapshot_verbose)
                if snapshot.strip():
                    return preferred
                failures += 1
                continue

            about_blank = next((page for page in pages if page.url.strip().lower() == "about:blank"), None)
            if about_blank:
                await self.select_page(about_blank.page_id)
                await self.navigate_page(self.settings.boss_home_url)
                if await self.wait_for_text(BOSS_PAGE_TEXTS, self.settings.action_timeout_ms):
                    snapshot = await self.take_snapshot(verbose=self.settings.snapshot_verbose)
                    if snapshot.strip():
                        return BrowserPage(page_id=about_blank.page_id, title=about_blank.title, url=self.settings.boss_home_url)
                failures += 1
                continue

            new_page = await self.new_page(self.settings.boss_home_url)
            if await self.wait_for_text(BOSS_PAGE_TEXTS, self.settings.action_timeout_ms):
                snapshot = await self.take_snapshot(verbose=self.settings.snapshot_verbose)
                if snapshot.strip():
                    return new_page
            failures += 1

        if failures >= 2:
            console_messages = await self.list_console_messages()
            network_requests = await self.list_network_requests()
            diagnostics = {
                "pages": [page.__dict__ for page in last_pages],
                "selected_page": self.selected_page.__dict__ if self.selected_page else None,
                "console_messages": console_messages,
                "failed_network_requests": [item for item in network_requests if str(item.get("status", ""))[:1] in {"4", "5"}],
                "mcp_command": self.settings.mcp_command,
                "mcp_args": self.settings.mcp_args,
                "possible_causes": [
                    "Chrome remote debugging was not ready",
                    "Chrome DevTools MCP was waiting for an Allow confirmation",
                ],
            }
            self.agent_logger.write_debug_json("latest_pages.json", diagnostics.get("pages"))
            raise BrowserPageNotReadyError(json.dumps(diagnostics, ensure_ascii=False, indent=2))

        raise BrowserPageNotReadyError("Unable to ensure a usable Boss page")


def _pick_boss_page(pages: list[BrowserPage]) -> BrowserPage | None:
    keywords = ["zhipin.com", "boss", "BOSS\u76f4\u8058", "Boss\u76f4\u8058"]
    for page in pages:
        haystack = f"{page.title} {page.url}"
        if any(keyword.lower() in haystack.lower() for keyword in keywords):
            return page
    return None


def _page_from_payload(payload: dict[str, Any], fallback_page_id: str = "") -> BrowserPage:
    items = _as_list(payload)
    if items:
        item = items[0]
        return BrowserPage(
            page_id=str(item.get("id") or item.get("pageId") or item.get("targetId") or fallback_page_id),
            title=str(item.get("title") or ""),
            url=str(item.get("url") or ""),
        )
    return BrowserPage(page_id=fallback_page_id, title=str(payload.get("title") or ""), url=str(payload.get("url") or ""))


def _result_to_dict(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        payload = result.model_dump()
    elif hasattr(result, "dict"):
        payload = result.dict()
    else:
        payload = {"content": getattr(result, "content", result), "structuredContent": getattr(result, "structuredContent", None)}
    return payload if isinstance(payload, dict) else {"value": payload}


def _as_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("structuredContent", "content", "pages", "items", "value"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        text = _extract_text(payload)
        parsed = _parse_json_like(text)
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        if isinstance(parsed, dict):
            for key in ("pages", "items"):
                value = parsed.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
    return []


def _extract_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        structured = payload.get("structuredContent")
        if isinstance(structured, (dict, list)):
            return json.dumps(structured, ensure_ascii=False)
        content = payload.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text") or item.get("content") or json.dumps(item, ensure_ascii=False)))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        if isinstance(content, str):
            return content
    return json.dumps(payload, ensure_ascii=False)


def _parse_json_like(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None
