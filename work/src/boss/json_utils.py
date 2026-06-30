from __future__ import annotations

import json
import re
from typing import Any, Dict


def robust_json_parse(raw: str) -> Dict[str, Any]:
    if not raw:
        return {}
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    candidates = [cleaned]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        candidates.append(cleaned[start : end + 1])
    for candidate in candidates:
        parsed = _try_parse(candidate)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _try_parse(text: str) -> Any:
    variants = [
        text,
        text.replace("，", ",").replace("：", ":"),
        re.sub(r",\s*([}\]])", r"\1", text),
    ]
    for variant in variants:
        try:
            return json.loads(variant)
        except json.JSONDecodeError:
            continue
    return None
