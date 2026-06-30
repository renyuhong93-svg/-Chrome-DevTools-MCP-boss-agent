from __future__ import annotations

import platform
import subprocess
import shutil
from typing import Any

from ollama import Client

from .exceptions import AgentConfigurationError, RuntimeDependencyError
from .settings import AgentSettings


def verify_runtime_environment(settings: AgentSettings) -> dict[str, Any]:
    if settings.run_mode != "browser_mcp_text_only":
        raise AgentConfigurationError(
            f"Unsupported RUN_MODE={settings.run_mode}, expected browser_mcp_text_only"
        )

    result: dict[str, Any] = {
        "node": _version("node", ["-v"]),
        "npm": _version("npm", ["-v"]),
        "npx": _version("npx", ["-v"]),
        "ollama": _version("ollama", ["--version"]),
    }

    failed = {name: info for name, info in result.items() if not info.get("ok")}
    if failed:
        messages = []
        for name, info in failed.items():
            messages.append(f"{name}: {info.get('error')}")
        raise RuntimeDependencyError(
            "Runtime dependency check failed:\n"
            + "\n".join(messages)
            + "\n\nPlease check PATH, restart PowerShell, or reinstall the missing dependency."
        )

    available_models = _ollama_models(settings)
    if settings.llm_model not in available_models:
        raise RuntimeDependencyError(
            f"Current Ollama installation does not include {settings.llm_model}. "
            f"Please run `ollama pull {settings.llm_model}` and try again."
        )

    result["llm_model"] = {
        "ok": True,
        "name": settings.llm_model,
    }
    result["available_models"] = sorted(available_models)
    return result


def _resolve_command(name: str) -> str | None:
    path = shutil.which(name)
    if path:
        return path

    if platform.system().lower() == "windows":
        for suffix in (".cmd", ".exe", ".bat"):
            path = shutil.which(name + suffix)
            if path:
                return path

    return None


def _version(name: str, args: list[str]) -> dict[str, Any]:
    exe = _resolve_command(name)
    if not exe:
        return {
            "ok": False,
            "name": name,
            "path": None,
            "error": f"{name} not found in PATH",
        }

    try:
        completed = subprocess.run(
            [exe, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=True,
        )
        return {
            "ok": True,
            "name": name,
            "path": exe,
            "version": (completed.stdout or completed.stderr).strip(),
        }
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "name": name,
            "path": exe,
            "error": f"FileNotFoundError: {exc}",
        }
    except subprocess.CalledProcessError as exc:
        return {
            "ok": False,
            "name": name,
            "path": exe,
            "error": (exc.stderr or exc.stdout or str(exc)).strip(),
        }
    except Exception as exc:
        return {
            "ok": False,
            "name": name,
            "path": exe,
            "error": repr(exc),
        }


def _ollama_models(settings: AgentSettings) -> set[str]:
    client = Client(host=settings.llm_base_url.removesuffix("/v1"))
    response = client.list()
    models = response.get("models", []) if isinstance(response, dict) else getattr(response, "models", [])

    names: set[str] = set()
    for item in models:
        if isinstance(item, dict):
            name = item.get("model") or item.get("name")
        else:
            name = getattr(item, "model", None) or getattr(item, "name", None)

        if name:
            names.add(str(name))

    return names