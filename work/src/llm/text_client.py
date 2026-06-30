from __future__ import annotations

import asyncio
import time

from openai import OpenAI

from src.core.settings import AgentSettings
from src.llm.env import configure_local_ollama_env


class TextLLMClient:
    def __init__(self, settings: AgentSettings, client: OpenAI | None = None):
        configure_local_ollama_env()
        self.settings = settings
        self.model = settings.llm_model
        self.timeout = float(settings.llm_timeout)
        self.temperature = float(settings.llm_temperature)
        self.max_retries = int(settings.llm_max_retries)
        self.retry_delay = float(settings.llm_retry_delay)
        self.client = client or OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=self.timeout,
        )

    async def chat(self, prompt: str) -> str:
        return await asyncio.to_thread(self._request_with_retry, prompt)

    def _request_with_retry(self, prompt: str) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 2):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                    timeout=self.timeout,
                )
                return (response.choices[0].message.content or "").strip()
            except Exception as exc:
                last_error = exc
                time.sleep(self.retry_delay * attempt)
        raise RuntimeError(f"LLM request failed after retries: {last_error}")
