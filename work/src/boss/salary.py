from __future__ import annotations

import re

from .models import SalaryRequirement


def parse_salary_requirement(text: str) -> SalaryRequirement | None:
    raw = text or ""
    day_match = re.search(
        r"(?:\u65e5\u85aa|\u6bcf\u5929|\u6bcf\u65e5)?\s*(\u5927\u4e8e|\u9ad8\u4e8e|\u8d85\u8fc7|\u4e0d\u5c11\u4e8e|\u81f3\u5c11|>=|>|"
        r"\u4ee5\u4e0a)?\s*(\d+(?:\.\d+)?)\s*(?:\u5143)?(?:/\u5929|/\u65e5)?",
        raw,
        re.I,
    )
    if day_match:
        amount = float(day_match.group(2))
        return SalaryRequirement(min_amount=amount, amount=amount, operator=_operator(day_match.group(1)), unit="day", raw=day_match.group(0))
    month_match = re.search(
        r"(?:\u6708\u85aa|\u85aa\u8d44|\u5de5\u8d44)?\s*(\u5927\u4e8e|\u9ad8\u4e8e|\u8d85\u8fc7|\u4e0d\u5c11\u4e8e|\u81f3\u5c11|>=|>|"
        r"\u4ee5\u4e0a)?\s*(\d+(?:\.\d+)?)\s*[kK]",
        raw,
        re.I,
    )
    if month_match:
        amount = float(month_match.group(2))
        return SalaryRequirement(min_amount=amount, amount=amount, operator=_operator(month_match.group(1)), unit="month_k", raw=month_match.group(0))
    return None


def parse_job_salary(text: str) -> tuple[float | None, float | None, str]:
    raw = (text or "").strip()
    if not raw or "\u9762\u8bae" in raw:
        return None, None, "unknown"

    day_match = re.search(
        r"(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?\s*(?:\u5143)?(?:/\u5929|/\u65e5|\u6bcf\u5929|\u6bcf\u65e5)",
        raw,
        re.I,
    )
    if day_match:
        salary_min = float(day_match.group(1))
        salary_max = float(day_match.group(2)) if day_match.group(2) else salary_min
        return salary_min, salary_max, "day"

    month_match = re.search(r"(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?\s*[kK]", raw)
    if month_match:
        salary_min = float(month_match.group(1))
        salary_max = float(month_match.group(2)) if month_match.group(2) else salary_min
        return salary_min, salary_max, "month_k"

    yuan_match = re.search(r"(\d{4,6})(?:-(\d{4,6}))?\s*\u5143/\u6708", raw, re.I)
    if yuan_match:
        salary_min = float(yuan_match.group(1)) / 1000
        salary_max = float(yuan_match.group(2)) / 1000 if yuan_match.group(2) else salary_min
        return salary_min, salary_max, "month_k"

    return None, None, "unknown"


def _operator(text: str | None) -> str:
    return ">" if text in {"\u5927\u4e8e", "\u9ad8\u4e8e", "\u8d85\u8fc7", ">"} else ">="
