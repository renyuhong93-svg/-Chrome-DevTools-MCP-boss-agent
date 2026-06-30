from __future__ import annotations

from loguru import logger

from src.core.settings import AgentSettings

from .text_client import TextLLMClient


class LLMManager:
    def __init__(self, settings: AgentSettings):
        self.text_client = TextLLMClient(settings)
        logger.info("llm text model={}", self.text_client.model)
