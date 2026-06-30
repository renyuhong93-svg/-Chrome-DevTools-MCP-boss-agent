from __future__ import annotations

from dataclasses import asdict
from typing import Any

from loguru import logger

from src.browser import BrowserMCPClient, SnapshotParser
from src.boss.matching import evaluate_job, match_job
from src.boss.models import BossContext, BossState, BrowserPageInfo, JobCard, JobDetail, job_key
from src.core.exceptions import BrowserPageNotReadyError
from src.core.logging_utils import AgentLogger

SEARCH_HINTS = ["\u641c\u7d22", "\u641c\u7d22\u804c\u4f4d", "\u804c\u4f4d", "\u516c\u53f8"]
RESULT_READY_TEXTS = ["\u804c\u4f4d", "\u7acb\u5373\u6c9f\u901a", "\u7b5b\u9009", "BOSS\u76f4\u8058"]
BLOCKER_TEXTS = ["\u767b\u5f55", "\u9a8c\u8bc1\u7801", "\u5b89\u5168\u9a8c\u8bc1", "\u98ce\u63a7\u63d0\u793a", "\u624b\u673a\u9a8c\u8bc1"]
DIALOG_TEXTS = ["\u786e\u5b9a", "\u53d1\u9001", "\u7ee7\u7eed", "\u77e5\u9053\u4e86"]


class BossStateMachine:
    def __init__(self, browser: BrowserMCPClient, llm_client: Any, agent_logger: AgentLogger, settings: Any):
        self.browser = browser
        self.llm_client = llm_client
        self.agent_logger = agent_logger
        self.settings = settings

    async def run(self, context: BossContext) -> BossContext:
        steps = 0
        while context.state not in {BossState.DONE, BossState.FAILED}:
            steps += 1
            if steps > self.settings.max_steps:
                context.stop_reason = f"Reached MAX_STEPS={self.settings.max_steps}"
                context.state = BossState.DONE
                break
            await self._log_state(context, action="enter")
            handler = getattr(self, f"_handle_{context.state.value.lower()}")
            context.state = await handler(context)
        return context

    async def _handle_init(self, context: BossContext) -> BossState:
        return BossState.CHECK_ENV

    async def _handle_check_env(self, context: BossContext) -> BossState:
        return BossState.CONNECT_BROWSER

    async def _handle_connect_browser(self, context: BossContext) -> BossState:
        return BossState.ENSURE_BOSS_PAGE

    async def _handle_ensure_boss_page(self, context: BossContext) -> BossState:
        try:
            page = await self.browser.ensure_boss_page()
        except BrowserPageNotReadyError as exc:
            context.stop_reason = str(exc)
            return BossState.FAILED
        context.current_page = BrowserPageInfo(page_id=page.page_id, title=page.title, url=page.url)
        context.current_snapshot = await self.browser.take_snapshot(verbose=self.settings.snapshot_verbose)
        return BossState.SEARCH_HOME

    async def _handle_search_home(self, context: BossContext) -> BossState:
        parser = SnapshotParser(context.current_snapshot)
        search_input = parser.find_input_by_keywords(SEARCH_HINTS)
        if search_input is None:
            search_input_uid = await self._find_uid_with_dom(
                """
                (() => {
                  const nodes = [...document.querySelectorAll('input, textarea, [role="searchbox"], [role="textbox"]')];
                  const target = nodes.find(node => {
                    const text = [node.placeholder, node.getAttribute?.('aria-label'), node.getAttribute?.('placeholder'), node.innerText]
                      .filter(Boolean).join(' ');
                    return text.includes('\\u641c\\u7d22') || text.includes('\\u804c\\u4f4d') || text.includes('\\u516c\\u53f8');
                  });
                  return target?.getAttribute('data-uid') || target?.id || '';
                })()
                """
            )
            if not search_input_uid:
                context.stop_reason = "Could not locate the search input on the Boss home page"
                return BossState.FAILED
            await self.browser.fill(search_input_uid, context.objective.search_keywords)
        else:
            await self.browser.fill(search_input.uid, context.objective.search_keywords)
        await self.browser.press_key("Enter")
        context.search_submitted = True
        return BossState.WAIT_RESULTS

    async def _handle_wait_results(self, context: BossContext) -> BossState:
        ready = await self.browser.wait_for_text(RESULT_READY_TEXTS, self.settings.action_timeout_ms)
        if not ready:
            context.stop_reason = "Search results did not become ready in time"
            return BossState.FAILED
        context.current_snapshot = await self.browser.take_snapshot(verbose=self.settings.snapshot_verbose)
        if not context.objective.need_hr_chat:
            context.stop_reason = "Search results page reached - search-only mode"
            return BossState.DONE
        return BossState.SCAN_JOB_LIST

    async def _handle_scan_job_list(self, context: BossContext) -> BossState:
        context.current_snapshot = await self.browser.take_snapshot(verbose=self.settings.snapshot_verbose)
        parser = SnapshotParser(context.current_snapshot)
        cards = [JobCard(**card, raw=card) for card in parser.find_job_cards()]
        for card in cards:
            key = job_key(card)
            if key and key not in context.visited_job_keys:
                context.current_job = card
                context.current_job_key = key
                return BossState.OPEN_JOB_DETAIL
        if context.scanned_jobs >= self.settings.max_job_scan:
            context.stop_reason = "Reached MAX_JOB_SCAN"
            return BossState.DONE
        return BossState.SCROLL_JOB_LIST

    async def _handle_open_job_detail(self, context: BossContext) -> BossState:
        if context.current_job is None:
            return BossState.SCAN_JOB_LIST
        await self.browser.click(context.current_job.uid)
        return BossState.READ_JOB_DETAIL

    async def _handle_read_job_detail(self, context: BossContext) -> BossState:
        snapshot = await self.browser.take_snapshot(verbose=self.settings.snapshot_verbose)
        parser = SnapshotParser(snapshot)
        detail_text = parser.find_detail_panel_text()
        communicate = parser.find_communication_button()
        if len(detail_text.strip()) < 120 and context.detail_reads < 2:
            await self.scroll_job_detail()
            context.detail_reads += 1
            return BossState.READ_JOB_DETAIL
        if len(detail_text.strip()) < 120:
            dom_detail = await self._read_detail_text_via_dom()
            if dom_detail:
                detail_text = dom_detail

        context.current_snapshot = detail_text
        context.current_detail = JobDetail(
            title=context.current_job.title if context.current_job else "",
            company=context.current_job.company if context.current_job else "",
            salary_text=context.current_job.salary_text if context.current_job else "",
            location=context.current_job.location_text if context.current_job else "",
            description_text=detail_text,
            raw_text=detail_text,
            communicate_uid=communicate.uid if communicate else "",
        )
        context.detail_reads = 0
        return BossState.EVALUATE_JOB

    async def _handle_evaluate_job(self, context: BossContext) -> BossState:
        if context.current_detail is None:
            context.stop_reason = "No job detail available for evaluation"
            return BossState.FAILED
        result = match_job(context.objective, context.current_detail)
        context.last_evaluation = await evaluate_job(self.llm_client, context.objective, context.current_detail, result)
        self.agent_logger.write_debug_json(
            "latest_evaluation.json",
            {
                "job_key": context.current_job_key,
                "job_detail_summary": context.current_detail.description_text[:1000],
                "rule_check_result": context.last_evaluation.rule_check_result,
                "llm_result": context.last_evaluation.llm_result,
                "final_match": context.last_evaluation.match,
            },
        )
        if context.last_evaluation.match and context.objective.need_hr_chat:
            return BossState.COMMUNICATE
        return BossState.NEXT_JOB

    async def _handle_communicate(self, context: BossContext) -> BossState:
        if context.current_detail is None or context.current_job is None or context.last_evaluation is None:
            return BossState.NEXT_JOB
        detail_key = job_key(context.current_detail)
        if detail_key and context.current_job_key and detail_key != context.current_job_key:
            context.skipped_reasons["detail_mismatch"] = context.skipped_reasons.get("detail_mismatch", 0) + 1
            return BossState.NEXT_JOB

        parser = SnapshotParser(await self.browser.take_snapshot(verbose=self.settings.snapshot_verbose))
        blocker = parser.find_by_text(BLOCKER_TEXTS)
        if blocker:
            context.encountered_blocker = blocker[0].text or blocker[0].name or blocker[0].raw
            context.stop_reason = "Manual verification required before continuing"
            return BossState.DONE

        button = parser.find_communication_button()
        if button is None and context.current_detail.communicate_uid:
            await self.browser.click(context.current_detail.communicate_uid)
        elif button is not None:
            await self.browser.click(button.uid)
        else:
            context.skipped_reasons["missing_communicate_button"] = context.skipped_reasons.get("missing_communicate_button", 0) + 1
            return BossState.NEXT_JOB

        await self._handle_common_dialogs()
        context.communication_count += 1
        context.successful_jobs.append(
            {
                "title": context.current_detail.title,
                "company": context.current_detail.company,
                "salary": context.current_detail.salary_text,
                "url": context.current_page.url,
                "reasons": context.last_evaluation.reasons,
            }
        )
        if context.communication_count >= self.settings.max_communications:
            context.stop_reason = "Reached MAX_COMMUNICATIONS"
            return BossState.DONE
        return BossState.NEXT_JOB

    async def _handle_next_job(self, context: BossContext) -> BossState:
        if context.current_job_key:
            context.visited_job_keys.add(context.current_job_key)
        context.scanned_jobs += 1
        context.current_job = None
        context.current_job_key = ""
        context.current_detail = None
        context.last_evaluation = None
        return BossState.SCAN_JOB_LIST if context.scanned_jobs < self.settings.max_job_scan else BossState.DONE

    async def _handle_scroll_job_list(self, context: BossContext) -> BossState:
        await self.scroll_job_list()
        return BossState.SCAN_JOB_LIST

    async def _handle_done(self, context: BossContext) -> BossState:
        return BossState.DONE

    async def _handle_failed(self, context: BossContext) -> BossState:
        return BossState.FAILED

    async def scroll_job_list(self) -> None:
        result = await self.browser.evaluate_script(
            """
            (() => {
              const candidates = [...document.querySelectorAll('*')].filter(node => node.scrollHeight > node.clientHeight + 120);
              const target = candidates.find(node => /job|list|recommend|search/.test((node.className || '') + ' ' + (node.id || ''))) || candidates[0];
              if (!target) return { scrolled: false };
              target.scrollBy(0, Math.max(600, Math.floor(target.clientHeight * 0.7)));
              return { scrolled: true };
            })()
            """
        )
        if "false" in str(result).lower():
            await self.browser.press_key("PageDown")

    async def scroll_job_detail(self) -> None:
        await self.browser.evaluate_script(
            """
            (() => {
              const candidates = [...document.querySelectorAll('*')].filter(node => node.scrollHeight > node.clientHeight + 120);
              const target = candidates.find(node => /detail|job-detail|content|main/.test((node.className || '') + ' ' + (node.id || ''))) || candidates.at(-1);
              if (!target) return { scrolled: false };
              target.scrollBy(0, Math.max(500, Math.floor(target.clientHeight * 0.7)));
              return { scrolled: true };
            })()
            """
        )

    async def _read_detail_text_via_dom(self) -> str:
        payload = await self.browser.evaluate_script(
            """
            (() => {
              const selectors = ['[class*="detail"]', '[class*="job-detail"]', 'main', 'section'];
              for (const selector of selectors) {
                const node = document.querySelector(selector);
                if (node && node.innerText && node.innerText.trim().length > 80) {
                  return node.innerText;
                }
              }
              return document.body ? document.body.innerText : '';
            })()
            """
        )
        text = str(payload.get("result", {}).get("structuredContent") or payload.get("result", {}).get("content") or payload)
        return text.strip()

    async def _find_uid_with_dom(self, script: str) -> str:
        payload = await self.browser.evaluate_script(script)
        text = str(payload.get("result", {}).get("structuredContent") or payload.get("result", {}).get("content") or "")
        return text.strip().strip('"')

    async def _handle_common_dialogs(self) -> None:
        parser = SnapshotParser(await self.browser.take_snapshot(verbose=self.settings.snapshot_verbose))
        for keyword in DIALOG_TEXTS:
            button = parser.find_button_by_keywords([keyword])
            if button is not None:
                await self.browser.click(button.uid)

    async def _log_state(self, context: BossContext, action: str) -> None:
        payload = {
            "state": context.state.value,
            "url": context.current_page.url,
            "title": context.current_page.title,
            "action": action,
            "uid": context.current_job.uid if context.current_job else "",
            "snapshot_summary": context.current_snapshot[:400],
            "llm_output": asdict(context.last_evaluation) if context.last_evaluation else None,
            "retry_counts": context.retry_counts,
            "result": context.stop_reason,
        }
        logger.info("state={} url={} action={} uid={}", payload["state"], payload["url"], payload["action"], payload["uid"])
        if self.settings.debug_dump:
            self.agent_logger.write_debug_json("latest_state.json", payload)
