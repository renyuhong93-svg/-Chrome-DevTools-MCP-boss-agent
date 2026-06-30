from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BossState(str, Enum):
    INIT = "INIT"
    CHECK_ENV = "CHECK_ENV"
    CONNECT_BROWSER = "CONNECT_BROWSER"
    ENSURE_BOSS_PAGE = "ENSURE_BOSS_PAGE"
    SEARCH_HOME = "SEARCH_HOME"
    WAIT_RESULTS = "WAIT_RESULTS"
    SCAN_JOB_LIST = "SCAN_JOB_LIST"
    OPEN_JOB_DETAIL = "OPEN_JOB_DETAIL"
    READ_JOB_DETAIL = "READ_JOB_DETAIL"
    EVALUATE_JOB = "EVALUATE_JOB"
    COMMUNICATE = "COMMUNICATE"
    NEXT_JOB = "NEXT_JOB"
    SCROLL_JOB_LIST = "SCROLL_JOB_LIST"
    DONE = "DONE"
    FAILED = "FAILED"


@dataclass
class SalaryRequirement:
    min_amount: float | None = None
    max_amount: float | None = None
    amount: float | None = None
    operator: str = ""
    unit: str = ""
    raw: str = ""


@dataclass
class UserObjective:
    raw_text: str
    search_keywords: str = ""
    job_titles: list[str] = field(default_factory=list)
    city: str = ""
    salary_requirement: SalaryRequirement | None = None
    job_type: str = ""
    experience_requirement: str = ""
    education_requirement: str = ""
    exclude_keywords: list[str] = field(default_factory=list)
    actions_allowed: list[str] = field(default_factory=list)
    target_count: int = 1
    need_hr_chat: bool = False


@dataclass
class BrowserPageInfo:
    page_id: str = ""
    title: str = ""
    url: str = ""


@dataclass
class JobCard:
    uid: str
    title: str = ""
    company: str = ""
    salary_text: str = ""
    location_text: str = ""
    text: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class JobDetail:
    title: str = ""
    company: str = ""
    salary_text: str = ""
    location: str = ""
    experience: str = ""
    education: str = ""
    skills: list[str] = field(default_factory=list)
    responsibilities: str = ""
    requirements: str = ""
    company_info: str = ""
    description_text: str = ""
    communicate_uid: str = ""
    raw_text: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchResult:
    matched: bool
    score: float = 0.0
    reject_reasons: list[str] = field(default_factory=list)
    positive_reasons: list[str] = field(default_factory=list)


@dataclass
class JobEvaluation:
    match: bool = False
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)
    rule_check_result: dict[str, Any] = field(default_factory=dict)
    llm_result: dict[str, Any] = field(default_factory=dict)


@dataclass
class BossContext:
    objective: UserObjective
    state: BossState = BossState.INIT
    current_page: BrowserPageInfo = field(default_factory=BrowserPageInfo)
    current_snapshot: str = ""
    scanned_jobs: int = 0
    communication_count: int = 0
    visited_job_keys: set[str] = field(default_factory=set)
    skipped_reasons: dict[str, int] = field(default_factory=dict)
    successful_jobs: list[dict[str, Any]] = field(default_factory=list)
    current_job: JobCard | None = None
    current_job_key: str = ""
    current_detail: JobDetail | None = None
    detail_reads: int = 0
    last_evaluation: JobEvaluation | None = None
    retry_counts: dict[str, int] = field(default_factory=dict)
    stop_reason: str = ""
    encountered_blocker: str = ""
    search_submitted: bool = False


def job_key(job: JobCard | JobDetail | None) -> str:
    if job is None:
        return ""
    if isinstance(job, JobDetail):
        parts = [job.title, job.company, job.salary_text, job.location]
    else:
        parts = [job.title, job.company, job.salary_text, job.location_text]
    return " | ".join(part.strip() for part in parts if part and part.strip())
