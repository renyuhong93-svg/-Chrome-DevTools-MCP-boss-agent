from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SnapshotElement:
    uid: str
    role: str = ""
    name: str = ""
    text: str = ""
    disabled: bool = False
    selected: bool = False
    raw: str = ""

    @property
    def haystack(self) -> str:
        return " ".join([self.role, self.name, self.text]).strip().lower()


@dataclass
class SnapshotParser:
    snapshot_text: str
    elements: list[SnapshotElement] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.elements:
            self.elements = self._parse_elements(self.snapshot_text)

    def find_by_text(self, texts: list[str]) -> list[SnapshotElement]:
        targets = [text.lower() for text in texts if text]
        return [element for element in self.elements if any(target in element.haystack for target in targets)]

    def find_input_by_keywords(self, keywords: list[str]) -> SnapshotElement | None:
        candidates = [element for element in self.find_by_text(keywords) if element.role in {"textbox", "searchbox", "input"}]
        return candidates[0] if candidates else None

    def find_button_by_keywords(self, keywords: list[str]) -> SnapshotElement | None:
        candidates = [element for element in self.find_by_text(keywords) if element.role in {"button", "link", "menuitem"}]
        return candidates[0] if candidates else None

    def find_job_cards(self) -> list[dict[str, str]]:
        cards: list[dict[str, str]] = []
        for block in self._split_job_blocks():
            text = " ".join(block)
            uid = self._find_uid_in_lines(block)
            if not uid:
                continue
            title = self._find_first(block, [r"职位[:：]\s*(.+)", r"岗位[:：]\s*(.+)"]) or block[0]
            company = self._find_first(block, [r"公司[:：]\s*(.+)"])
            salary = self._find_first(block, [r"薪资[:：]\s*(.+)", r"\d+(?:-\d+)?[Kk元/天月]"])
            location = self._find_first(block, [r"地点[:：]\s*(.+)", r"城市[:：]\s*(.+)"])
            cards.append(
                {
                    "uid": uid,
                    "title": _clean(title),
                    "company": _clean(company),
                    "salary_text": _clean(salary),
                    "location_text": _clean(location),
                    "text": _clean(text),
                }
            )
        return cards

    def find_detail_panel_text(self) -> str:
        markers = ["职位描述", "岗位职责", "任职要求", "公司介绍", "职位详情"]
        lines = self.snapshot_text.splitlines()
        for index, line in enumerate(lines):
            if any(marker in line for marker in markers):
                return "\n".join(lines[index:]).strip()
        return self.snapshot_text.strip()

    def find_communication_button(self) -> SnapshotElement | None:
        return self.find_button_by_keywords(["立即沟通", "继续沟通", "开始沟通"])

    def find_possible_scroll_regions(self) -> list[str]:
        regions = []
        text = self.snapshot_text.lower()
        if "职位列表" in self.snapshot_text or "job-list" in text:
            regions.append("job_list")
        if "职位描述" in self.snapshot_text or "job-detail" in text or "detail" in text:
            regions.append("job_detail")
        return regions

    def _parse_elements(self, snapshot_text: str) -> list[SnapshotElement]:
        elements: list[SnapshotElement] = []
        for line in snapshot_text.splitlines():
            uid_match = re.search(r"(?:uid|id)\s*[:=]\s*['\"]?([\w:-]+)", line, re.I)
            if not uid_match:
                continue
            role = _match_group(line, r"role\s*[:=]\s*['\"]?([\w-]+)") or _infer_role(line)
            name = _match_group(line, r"name\s*[:=]\s*['\"]([^'\"]+)")
            text = _match_group(line, r"text\s*[:=]\s*['\"]([^'\"]+)") or _strip_tags(line)
            elements.append(
                SnapshotElement(
                    uid=uid_match.group(1),
                    role=role,
                    name=name,
                    text=text,
                    disabled="disabled" in line.lower(),
                    selected="selected" in line.lower(),
                    raw=line,
                )
            )
        return elements

    def _split_job_blocks(self) -> list[list[str]]:
        lines = [line.strip() for line in self.snapshot_text.splitlines() if line.strip()]
        blocks: list[list[str]] = []
        current: list[str] = []
        for line in lines:
            if re.search(r"(职位|岗位|薪资|公司|地点|经验|学历)", line) and current:
                if len(current) >= 3:
                    blocks.append(current)
                    current = []
            current.append(line)
        if current:
            blocks.append(current)
        return [block for block in blocks if any("职位" in line or "岗位" in line for line in block)]

    def _find_uid_in_lines(self, lines: list[str]) -> str:
        for line in lines:
            match = re.search(r"(?:uid|id)\s*[:=]\s*['\"]?([\w:-]+)", line, re.I)
            if match:
                return match.group(1)
        return ""

    def _find_first(self, lines: list[str], patterns: list[str]) -> str:
        for line in lines:
            for pattern in patterns:
                match = re.search(pattern, line, re.I)
                if match:
                    return match.group(1) if match.groups() else match.group(0)
        return ""


def _match_group(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.I)
    return match.group(1).strip() if match else ""


def _infer_role(text: str) -> str:
    lower = text.lower()
    if "button" in lower:
        return "button"
    if "input" in lower or "textbox" in lower or "searchbox" in lower:
        return "input"
    if "link" in lower:
        return "link"
    return ""


def _strip_tags(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" :-")
