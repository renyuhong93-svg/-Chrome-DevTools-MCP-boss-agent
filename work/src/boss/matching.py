from __future__ import annotations

import json
from typing import Any

from src.boss.json_utils import robust_json_parse

from .models import JobDetail, JobEvaluation, MatchResult, UserObjective
from .salary import parse_job_salary

ROLE_ALIASES = {
    "\u524d\u7aef": ["\u524d\u7aef", "web", "vue", "react", "h5", "javascript", "js", "typescript", "ts"],
    "\u540e\u7aef": ["\u540e\u7aef", "java", "python", "go", "golang", "php"],
    "\u7b97\u6cd5": ["\u7b97\u6cd5", "\u673a\u5668\u5b66\u4e60", "\u6df1\u5ea6\u5b66\u4e60", "nlp", "\u63a8\u8350", "\u5927\u6a21\u578b", "agent"],
}

UNLIMITED_EXPERIENCE = "\u7ecf\u9a8c\u4e0d\u9650"
UNLIMITED_EDUCATION = "\u5b66\u5386\u4e0d\u9650"
REMOTE = "\u8fdc\u7a0b"


def match_job(task: UserObjective, job: JobDetail) -> MatchResult:
    positives: list[str] = []
    rejects: list[str] = []
    score = 0.0
    haystack = " ".join(
        [
            job.title,
            job.company,
            job.location,
            job.experience,
            job.education,
            " ".join(job.skills),
            job.description_text,
        ]
    ).lower()

    for keyword in task.exclude_keywords:
        if keyword and keyword.lower() in haystack:
            rejects.append(f"Contains excluded keyword: {keyword}")

    if task.job_titles:
        matched_titles = [title for title in task.job_titles if _role_matches(title, haystack)]
        if matched_titles:
            score += 35
            positives.append(f"Role matches: {', '.join(matched_titles)}")
        else:
            rejects.append(f"Role mismatch: expected one of {', '.join(task.job_titles)}")

    if task.city and task.city != REMOTE:
        if task.city.lower() in haystack:
            score += 15
            positives.append(f"City matches: {task.city}")
        else:
            rejects.append(f"City mismatch: expected {task.city}, got {job.location or 'unknown'}")

    if task.job_type:
        if task.job_type.lower() in haystack:
            score += 12
            positives.append(f"Job type matches: {task.job_type}")
        elif task.job_type == REMOTE:
            rejects.append("Job is not remote")

    if task.education_requirement:
        if _education_ok(task.education_requirement, job.education, haystack):
            score += 8
            positives.append(f"Education fits: {job.education or task.education_requirement}")
        else:
            rejects.append(f"Education mismatch: expected {task.education_requirement}, got {job.education or 'unknown'}")

    if task.experience_requirement:
        if task.experience_requirement.lower() in haystack or UNLIMITED_EXPERIENCE in haystack:
            score += 8
            positives.append(f"Experience fits: {task.experience_requirement}")
        else:
            rejects.append(f"Experience mismatch: expected {task.experience_requirement}")

    salary_requirement = task.salary_requirement
    if salary_requirement and (salary_requirement.min_amount is not None or salary_requirement.amount is not None):
        required = salary_requirement.min_amount if salary_requirement.min_amount is not None else salary_requirement.amount
        salary_min, salary_max, salary_unit = parse_job_salary(job.salary_text)
        if salary_min is None or salary_unit == "unknown":
            rejects.append(f"Unable to parse salary: {job.salary_text or 'unknown'}")
        elif not _salary_units_compatible(salary_unit, salary_requirement.unit):
            rejects.append(f"Salary unit mismatch: expected {salary_requirement.unit}, got {salary_unit}")
        elif _salary_satisfies(salary_min, salary_max, required or 0, salary_requirement.operator, salary_unit, salary_requirement.unit):
            score += 25
            positives.append(f"Salary fits: {job.salary_text}")
        else:
            rejects.append(f"Salary too low: {job.salary_text}")

    if task.search_keywords and any(token.lower() in haystack for token in task.search_keywords.split()):
        score += 8
        positives.append(f"Search keywords hit: {task.search_keywords}")

    return MatchResult(matched=not rejects and score > 0, score=score, reject_reasons=rejects, positive_reasons=positives)


async def evaluate_job(
    llm_client: Any,
    task: UserObjective,
    detail: JobDetail,
    rule_result: MatchResult,
) -> JobEvaluation:
    llm_result: dict[str, Any] = {}
    if llm_client is not None:
        llm_result = await _evaluate_with_llm(llm_client, task, detail, rule_result)

    llm_match = bool(llm_result.get("match", rule_result.matched))
    llm_score = float(llm_result.get("score", rule_result.score / 100 if rule_result.score else 0.0))
    final_match = bool(rule_result.matched and llm_match)
    reasons = list(rule_result.positive_reasons) + [str(item) for item in llm_result.get("reasons", []) if item]
    risks = [str(item) for item in llm_result.get("risks", []) if item]
    missing_info = [str(item) for item in llm_result.get("missing_info", []) if item]
    if rule_result.reject_reasons:
        risks.extend(rule_result.reject_reasons)

    return JobEvaluation(
        match=final_match,
        score=llm_score,
        reasons=_unique(reasons),
        risks=_unique(risks),
        missing_info=_unique(missing_info),
        rule_check_result={
            "matched": rule_result.matched,
            "score": rule_result.score,
            "positive_reasons": rule_result.positive_reasons,
            "reject_reasons": rule_result.reject_reasons,
        },
        llm_result=llm_result,
    )


async def _evaluate_with_llm(llm_client: Any, task: UserObjective, detail: JobDetail, rule_result: MatchResult) -> dict[str, Any]:
    prompt = f"""
Return JSON only.
Decide whether this job matches the user goal.

User objective:
{json.dumps(task.__dict__, ensure_ascii=False)}

Rule precheck:
{json.dumps({
    "matched": rule_result.matched,
    "score": rule_result.score,
    "positive_reasons": rule_result.positive_reasons,
    "reject_reasons": rule_result.reject_reasons,
}, ensure_ascii=False)}

Job detail:
{json.dumps(detail.__dict__, ensure_ascii=False)}

Required JSON schema:
{{
  "match": true,
  "score": 0.82,
  "reasons": ["..."],
  "risks": ["..."],
  "missing_info": []
}}
"""
    raw = await llm_client.chat(prompt)
    parsed = robust_json_parse(raw)
    if parsed:
        return parsed
    repaired = robust_json_parse(await llm_client.chat(f"Fix this into valid JSON only:\n{raw}"))
    return repaired if repaired else {"match": False, "score": 0.0, "reasons": [], "risks": ["LLM did not return valid JSON"], "missing_info": []}


def _role_matches(role: str, text: str) -> bool:
    aliases = ROLE_ALIASES.get(role, [role])
    return any(alias.lower() in text for alias in aliases)


def _salary_units_compatible(job_unit: str, required_unit: str) -> bool:
    if not required_unit:
        return True
    if job_unit == required_unit:
        return True
    return {job_unit, required_unit} == {"month", "month_k"}


def _salary_satisfies(
    salary_min: float | None,
    salary_max: float | None,
    required: float,
    operator: str,
    job_unit: str,
    required_unit: str,
) -> bool:
    comparable = salary_min if required_unit == "day" else (salary_max if salary_max is not None else salary_min)
    if comparable is None:
        return False
    if job_unit == "month_k" and required_unit == "month":
        comparable *= 1000
    elif job_unit == "month" and required_unit == "month_k":
        comparable /= 1000
    return comparable > required if operator == ">" else comparable >= required


def _education_ok(required: str, actual: str, haystack: str) -> bool:
    if UNLIMITED_EDUCATION in haystack:
        return True
    order = {"\u5927\u4e13": 1, "\u672c\u79d1": 2, "\u7855\u58eb": 3, "\u535a\u58eb": 4}
    if required not in order:
        return required in haystack
    if not actual:
        return True
    actual_level = max((value for name, value in order.items() if name in actual), default=0)
    return actual_level <= order[required] if actual_level else True


def _unique(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result
