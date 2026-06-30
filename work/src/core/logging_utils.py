from __future__ import annotations

import json
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from .settings import AgentSettings


class AgentLogger:
    def __init__(self, settings: AgentSettings):
        self.settings = settings
        self.run_id = datetime.now().strftime("%H%M%S") + "_" + uuid.uuid4().hex[:6]
        self.today = datetime.now().strftime("%Y%m%d")
        self.root = Path(settings.logs_root)
        self.agent_dir = self.root / "agent" / self.today
        self.mcp_dir = self.root / "mcp" / self.today
        self.debug_dir = self.root / "debug"
        self.agent_dir.mkdir(parents=True, exist_ok=True)
        self.mcp_dir.mkdir(parents=True, exist_ok=True)
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.agent_dir / f"run_{self.run_id}.log"
        self.mcp_file = self.mcp_dir / f"mcp_{self.run_id}.jsonl"

    def write_debug_text(self, name: str, text: str) -> None:
        (self.debug_dir / name).write_text(text, encoding="utf-8")

    def write_debug_json(self, name: str, payload: Any) -> None:
        (self.debug_dir / name).write_text(json.dumps(_plain(payload), ensure_ascii=False, indent=2), encoding="utf-8")

    def write_mcp_event(self, event: dict[str, Any]) -> None:
        with self.mcp_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_plain(event), ensure_ascii=False) + "\n")


def setup_logging(agent_logger: AgentLogger) -> None:
    logger.remove()
    logger.add(agent_logger.log_file, encoding="utf-8", level="INFO")
    logger.add(lambda message: print(message, end=""), level="INFO")


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value
