from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class AgentSettings(BaseModel):
    run_mode: str = "browser_mcp_text_only"
    llm_provider: str = "ollama"
    llm_base_url: str = "http://127.0.0.1:11434/v1"
    llm_model: str = "Qwen3:8B"
    llm_api_key: str = "ollama"
    llm_timeout: float = 120.0
    llm_temperature: float = 0.1
    llm_max_retries: int = 2
    llm_retry_delay: float = 1.0
    mcp_command: str = "cmd"
    mcp_args: list[str] = Field(default_factory=lambda: ["/c", "npx", "-y", "chrome-devtools-mcp@latest", "--autoConnect"])
    boss_home_url: str = "https://www.zhipin.com/"
    max_communications: int = 2
    max_job_scan: int = 80
    max_steps: int = 120
    action_timeout_ms: int = 15000
    snapshot_verbose: bool = False
    debug_dump: bool = True
    logs_root: str = "logs"

    @property
    def mcp_command_display(self) -> str:
        return " ".join([self.mcp_command, *self.mcp_args])


def load_settings(dotenv_path: str | None = None) -> AgentSettings:
    root = Path(__file__).resolve().parents[2]
    load_dotenv(dotenv_path=dotenv_path or root / ".env", override=False)
    return AgentSettings(
        run_mode=_env("RUN_MODE", "browser_mcp_text_only"),
        llm_provider=_env("LLM_PROVIDER", "ollama"),
        llm_base_url=_normalize_base_url(_env("LLM_BASE_URL", "http://127.0.0.1:11434")),
        llm_model=_env("LLM_MODEL", "Qwen3:8B"),
        llm_api_key=_env("LLM_API_KEY", "ollama"),
        llm_timeout=_env_float("LLM_TIMEOUT", 120.0),
        llm_temperature=_env_float("LLM_TEMPERATURE", 0.1),
        llm_max_retries=_env_int("LLM_MAX_RETRIES", 2),
        llm_retry_delay=_env_float("LLM_RETRY_DELAY", 1.0),
        mcp_command=_env("MCP_COMMAND", "cmd"),
        mcp_args=_split_csv(_env("MCP_ARGS", "/c,npx,-y,chrome-devtools-mcp@latest,--autoConnect")),
        boss_home_url=_env("BOSS_HOME_URL", "https://www.zhipin.com/"),
        max_communications=_env_int("MAX_COMMUNICATIONS", 2),
        max_job_scan=_env_int("MAX_JOB_SCAN", 80),
        max_steps=_env_int("MAX_STEPS", 120),
        action_timeout_ms=_env_int("ACTION_TIMEOUT_MS", 15000),
        snapshot_verbose=_env_bool("SNAPSHOT_VERBOSE", False),
        debug_dump=_env_bool("DEBUG_DUMP", True),
        logs_root=_env("LOGS_ROOT", "logs"),
    )


def _env(name: str, default: str) -> str:
    return str(os.getenv(name, default)).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_base_url(value: str) -> str:
    text = value.rstrip("/")
    if text.endswith("/v1"):
        return text
    return f"{text}/v1"
