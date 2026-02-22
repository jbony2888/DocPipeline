from __future__ import annotations

import re


def _normalize_token_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def normalize_grade(raw_grade):
    """
    Canonical grade domain:
      - "K"
      - integers 1..12
    Returns (normalized_value, method)
    """
    if raw_grade is None:
        return None, "missing"
    raw = str(raw_grade).strip()
    if not raw:
        return None, "missing"

    lowered = raw.casefold()
    if lowered in {"k", "kindergarten", "kinder"}:
        return "K", "kindergarten_alias"

    # "Grade 1", "1st", "10th", "1"
    match = re.search(r"(-?\d+)", lowered)
    if not match:
        return None, "unparseable"
    val = int(match.group(1))
    if val == 0 or val < 0 or val > 12:
        return None, "invalid_range"
    if 1 <= val <= 12:
        if lowered == str(val):
            return val, "numeric"
        if "grade" in lowered:
            return val, "grade_prefix"
        if re.search(r"\d+(st|nd|rd|th)\b", lowered):
            return val, "ordinal"
        return val, "numeric_parse"
    return None, "unparseable"


def is_grade_missing(raw_grade) -> bool:
    return raw_grade is None or str(raw_grade).strip() == ""


def is_name_school_possible_swap(student_name, school_name) -> bool:
    if student_name is None or school_name is None:
        return False
    return _normalize_token_text(student_name) == _normalize_token_text(school_name)

