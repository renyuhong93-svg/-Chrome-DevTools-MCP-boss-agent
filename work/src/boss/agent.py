from __future__ import annotations

from dataclasses import asdict
from typing import Any

from loguru import logger

from src.browser import BrowserMCPClient
from src.core import load_settings, setup_logging, verify_runtime_environment
from src.core.logging_utils import AgentLogger
from src.llm.manager import LLMManager
from src.task.objective_parser import parse_user_objective

from .models import BossContext, BossState
from .state_machine import BossStateMachine


class BossBrowserAgent:
    def __init__(self, objective: str, dotenv_path: str | None = None, overrides: dict[str, Any] | None = None):
        self.settings = load_settings(dotenv_path)
        if overrides:
            self.settings = self.settings.model_copy(update={key: value for key, value in overrides.items() if value is not None})
        self.agent_logger = AgentLogger(self.settings)
        setup_logging(self.agent_logger)
        self.llm_manager = LLMManager(self.settings)
        self.objective = parse_user_objective(objective, llm_client=None)
        self.browser = BrowserMCPClient(self.settings, self.agent_logger)
        self.state_machine = BossStateMachine(self.browser, self.llm_manager.text_client, self.agent_logger, self.settings)

    async def start(self) -> BossContext:
        env_info = verify_runtime_environment(self.settings)
        logger.info("runtime mode={} env={}", self.settings.run_mode, env_info)
        logger.info("objective={}", asdict(self.objective))

        context = BossContext(objective=self.objective)
        await self.browser.start()
        try:
            context = await self.state_machine.run(context)
        finally:
            await self.browser.close()

        if context.state not in {BossState.DONE, BossState.FAILED}:
            context.state = BossState.DONE

        self.agent_logger.write_debug_json(
            "latest_summary.json",
            {
                "scanned_jobs": context.scanned_jobs,
                "communication_count": context.communication_count,
                "successful_jobs": context.successful_jobs,
                "skipped_reasons": context.skipped_reasons,
                "encountered_blocker": context.encountered_blocker,
                "log_file": str(self.agent_logger.log_file),
                "mcp_log_file": str(self.agent_logger.mcp_file),
            },
        )
        return context
