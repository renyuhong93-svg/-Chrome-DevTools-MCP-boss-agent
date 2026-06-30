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
        await client.ensure_boss_page()
        snapshot = await client.take_snapshot(verbose=settings.snapshot_verbose)
        agent_logger.write_debug_text("latest_snapshot.txt", snapshot)
        print("saved logs/debug/latest_snapshot.txt")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
