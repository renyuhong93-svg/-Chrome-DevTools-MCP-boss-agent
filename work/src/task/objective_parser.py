from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from src.boss.json_utils import robust_json_parse
from src.boss.models import SalaryRequirement, UserObjective

CITY_HINTS = [
    "\u5317\u4eac",
    "\u4e0a\u6d77",
    "\u5e7f\u5dde",
    "\u6df1\u5733",
    "\u676d\u5dde",
    "\u5357\u4eac",
    "\u6210\u90fd",
    "\u6b66\u6c49",
    "\u897f\u5b89",
    "\u82cf\u5dde",
    "\u8fdc\u7a0b",
]
JOB_HINTS = [
    "\u524d\u7aef",
    "\u540e\u7aef",
    "\u7b97\u6cd5",
    "Java",
    "Python",
    "React",
    "Vue",
    "AI Agent",
    "\u673a\u5668\u5b66\u4e60",
    "\u5b9e\u4e60",
    "\u6821\u62db",
]


@dataclass
class JobTask(UserObjective):
    actions_allowed: list[str] = field(default_factory=lambda: ["search", "open_detail", "scroll"])

    def model_dump(self) -> dict[str, Any]:
        return self.__dict__


def parse_user_objective(raw_text: str, llm_client: Any | None = None, default_target_count: int = 1) -> JobTask:
    raw = (raw_text or "").strip()
    task = JobTask(raw_text=raw)
    llm_data = _parse_with_llm(raw, llm_client)
    if llm_data:
        task.search_keywords = str(llm_data.get("search_keywords") or "")
        task.job_titles = [str(item) for item in llm_data.get("job_titles", []) if item]
        task.city = str(llm_data.get("city") or "")
        task.job_type = str(llm_data.get("job_type") or "")
        task.experience_requirement = str(llm_data.get("experience_requirement") or "")
        task.education_requirement = str(llm_data.get("education_requirement") or "")
        task.exclude_keywords = [str(item) for item in llm_data.get("exclude_keywords", []) if item]
        task.need_hr_chat = bool(llm_data.get("need_hr_chat"))
        task.target_count = int(llm_data.get("target_count") or default_target_count)
        salary = llm_data.get("salary_requirement")
        if isinstance(salary, dict):
            task.salary_requirement = SalaryRequirement(
                min_amount=_float_or_none(salary.get("min_amount", salary.get("amount"))),
                max_amount=_float_or_none(salary.get("max_amount")),
                amount=_float_or_none(salary.get("amount")),
                operator=str(salary.get("operator") or ""),
                unit=str(salary.get("unit") or ""),
                raw=str(salary.get("raw") or ""),
            )
    _apply_rules(task, default_target_count)
    return task


def parse_salary_requirement_from_text(raw_text: str) -> SalaryRequirement | None:
    text = raw_text or ""
    daily = re.search(
        r"(?:\u65e5\u85aa|\u6bcf\u5929|\u6bcf\u65e5|\u65e5\u7ed3)?\s*(\u5927\u4e8e|\u9ad8\u4e8e|\u8d85\u8fc7|\u4e0d\u5c11\u4e8e|\u81f3\u5c11|>=|>|"
        r"\u4ee5\u4e0a)?\s*(\d+(?:\.\d+)?)\s*(?:\u5143)?\s*(?:/\u5929|/\u65e5|\u6bcf\u5929|\u6bcf\u65e5)?",
        text,
        re.I,
    )
    if daily:
        amount = float(daily.group(2))
        return SalaryRequirement(min_amount=amount, amount=amount, operator=_operator(daily.group(1)), unit="day", raw=daily.group(0))
    monthly = re.search(
        r"(?:\u6708\u85aa|\u85aa\u8d44|\u5de5\u8d44)?\s*(\u5927\u4e8e|\u9ad8\u4e8e|\u8d85\u8fc7|\u4e0d\u5c11\u4e8e|\u81f3\u5c11|>=|>|"
        r"\u4ee5\u4e0a)?\s*(\d+(?:\.\d+)?)\s*[kK]",
        text,
        re.I,
    )
    if monthly:
        amount = float(monthly.group(2))
        return SalaryRequirement(min_amount=amount, amount=amount, operator=_operator(monthly.group(1)), unit="month_k", raw=monthly.group(0))
    return None


def _parse_with_llm(raw_text: str, llm_client: Any | None) -> dict[str, Any]:
    if not raw_text or llm_client is None:
        return {}
    prompt = f"""
Return JSON only. Parse the BOSS job-search objective into:
search_keywords, job_titles, city, salary_requirement, job_type,
experience_requirement, education_requirement, exclude_keywords,
target_count, need_hr_chat.

User input: {raw_text}
"""
    try:
        raw = asyncio.run(llm_client.chat(prompt))
    except Exception as exc:
        logger.warning("objective parse with llm failed: {}", exc)
        return {}
    parsed = robust_json_parse(raw)
    return parsed if isinstance(parsed, dict) else {}


def _apply_rules(task: JobTask, default_target_count: int) -> None:
    raw = task.raw_text
    if not task.city:
        task.city = _first_hit(raw, CITY_HINTS)
    if not task.job_titles:
        task.job_titles = [item for item in JOB_HINTS if item.lower() in raw.lower() and item != "\u5b9e\u4e60"]
    if not task.job_type:
        if "\u5b9e\u4e60" in raw:
            task.job_type = "\u5b9e\u4e60"
        elif "\u8fdc\u7a0b" in raw:
            task.job_type = "\u8fdc\u7a0b"
    if not task.salary_requirement:
        task.salary_requirement = parse_salary_requirement_from_text(raw)
    if not task.search_keywords:
        parts = task.job_titles + ([task.job_type] if task.job_type and task.job_type != "\u8fdc\u7a0b" else [])
        task.search_keywords = " ".join(parts).strip() or raw
    task.exclude_keywords = _unique(task.exclude_keywords + _exclude_keywords(raw))
    task.need_hr_chat = task.need_hr_chat or bool(
        re.search(r"(\u6c9f\u901a|\u8054\u7cfbHR|\u804a\u4e00\u804a|\u7acb\u5373\u6c9f\u901a)", raw, re.I)
    )
    if task.need_hr_chat and "chat" not in task.actions_allowed:
        task.actions_allowed.append("chat")
    task.target_count = task.target_count or default_target_count


def _exclude_keywords(text: str) -> list[str]:
    result: list[str] = []
    for match in re.finditer(r"(?:\u4e0d\u8981|\u6392\u9664|\u4e0d\u770b|\u907f\u5f00)([^\uff0c\u3002\uff1b;\n]+)", text):
        result.extend(part.strip() for part in re.split(r"[\u3001\u548c\u4e0e]", match.group(1)) if part.strip())
    return result


def _first_hit(text: str, options: list[str]) -> str:
    lower = text.lower()
    for option in options:
        if option.lower() in lower:
            return option
    return ""


def _operator(text: str | None) -> str:
    return ">" if text in {"\u5927\u4e8e", "\u9ad8\u4e8e", "\u8d85\u8fc7", ">"} else ">="


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unique(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result
