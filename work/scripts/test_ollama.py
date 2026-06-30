from __future__ import annotations

import asyncio

from src.core import load_settings
from src.llm.manager import LLMManager

PROMPT = """
Return JSON only.
判断这个岗位是否符合“前端实习，日薪大于200”：
岗位：React 前端实习生，薪资 220-300 元/天，地点 上海，要求熟悉 JavaScript、TypeScript、React。
"""


async def main() -> None:
    manager = LLMManager(load_settings())
    print(await manager.text_client.chat(PROMPT))


if __name__ == "__main__":
    asyncio.run(main())
