from __future__ import annotations

import asyncio

from src.browser import BrowserMCPClient
from src.core import AgentLogger, load_settings, setup_logging


async def main() -> None:
    settings = load_settings()
    agent_logger = AgentLogger(settings)
    setup_logging(agent_logger)
    client = BrowserMCPClient(settings, agent_logger)
    await client.start()
    try:
        for page in await client.list_pages():
            print(f"{page.title} | {page.url}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
