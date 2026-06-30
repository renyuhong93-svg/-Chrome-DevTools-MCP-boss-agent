from __future__ import annotations

import argparse
import asyncio

from src.boss.agent import BossBrowserAgent

DEFAULT_OBJECTIVE = "\u67e5\u627e\u524d\u7aef\u5b9e\u4e60\uff0c\u65e5\u85aa\u5927\u4e8e200\uff0c\u7b26\u5408\u7684\u8bdd\u70b9\u51fb\u7acb\u5373\u6c9f\u901a"
PROMPT = "\u8bf7\u8f93\u5165\u672c\u6b21 Agent \u8981\u5b8c\u6210\u7684\u76ee\u6807/\u8981\u5bfb\u627e\u7684\u5185\u5bb9: "


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BOSS browser MCP text-only agent")
    parser.add_argument("objective", nargs="*", help="Natural-language job-search goal")
    parser.add_argument("--max-steps", type=int, default=None, help="Override MAX_STEPS for this run")
    return parser.parse_args()


def objective_from_args(args: argparse.Namespace) -> str:
    text = " ".join(args.objective).strip()
    return text or input(PROMPT).strip() or DEFAULT_OBJECTIVE


async def main() -> None:
    args = parse_args()
    agent = BossBrowserAgent(objective_from_args(args), overrides={"max_steps": args.max_steps})
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
