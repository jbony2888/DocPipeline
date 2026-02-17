"""
Deterministic normalization helpers for grades and school names.
"""

import re
import string
from typing import Optional, Tuple, Union


GRADE_PATTERNS = [
    re.compile(r"grade[:\s]*([0-9]{1,2})", re.IGNORECASE),
    re.compile(r"([0-9]{1,2})(st|nd|rd|th)?\s*grade", re.IGNORECASE),
    re.compile(r"^([0-9]{1,2})$", re.IGNORECASE),
]

KINDER_TERMS = {"k", "kinder", "kindergarten", "kinder.", "k-grade"}


def is_valid_grade(grade: Optional[Union[int, str]]) -> bool:
    """
    Check if grade is valid (1-12 or K). Rejects out-of-range values (e.g. 40, 0, 13).
    """
    if grade is None or grade == "":
        return False
    if isinstance(grade, int):
        return 1 <= grade <= 12
    s = str(grade).strip().upper()
    if s.lower() in KINDER_TERMS:
        return True
    try:
        n = int(s)
        return 1 <= n <= 12
    except ValueError:
        return False


def sanitize_grade(grade: Optional[Union[int, str]]) -> Optional[Union[int, str]]:
    """
    Return grade only if valid (1-12 or K). Otherwise return None.
    Use this to reject OCR/LLM errors like 40, 0, 13.
    """
    if not is_valid_grade(grade):
        return None
    if isinstance(grade, int):
        return grade
    s = str(grade).strip().upper()
    if s.lower() in KINDER_TERMS:
        return "K"
    try:
        return int(s)
    except ValueError:
        return "K"  # kinder variant


def normalize_grade(grade_raw: Optional[str]) -> Tuple[Optional[int], str]:
    """
    Normalize grade strings to integer 1-12 or None for Kindergarten.
    
    Returns (grade_norm, reason)
    """
    if grade_raw is None:
        return None, "missing"
    text = str(grade_raw).strip()
    if not text:
        return None, "empty"
    if text.lower() in KINDER_TERMS:
        return None, "kinder"
    for pat in GRADE_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                val = int(m.group(1))
                if 1 <= val <= 12:
                    return val, "parsed"
            except ValueError:
                pass
    return None, "unparsed"


MIN_SCHOOL_NAME_LENGTH = 3

SCHOOL_MAP = {
    "rachel carson": "RACHEL_CARSON",
    "rachel carson school": "RACHEL_CARSON",
    "rachel carson elementary": "RACHEL_CARSON",
    "edwards": "EDWARDS",
    "edwards school": "EDWARDS",
    "escuela edwards": "EDWARDS",
}

# Known OCR typos / variants → canonical key for lookup (lowercase, no punctuation)
SCHOOL_TYPOS = {
    "dware": "edwards",
    "edward": "edwards",
    "edwards school": "edwards",
}


def _strip_leading_trailing_punctuation(text: str) -> str:
    """Remove punctuation only from start and end of string."""
    return text.strip(string.punctuation + " \t\n\r")


def sanitize_school_name(school_raw: Optional[str]) -> Optional[str]:
    """
    Clean noisy OCR output for school name.

    - Strip leading/trailing punctuation and trim whitespace
    - Collapse internal whitespace
    - Enforce minimum length >= 3; reject 1–2 character strings (return None)
    - Normalize casing (title case)

    Returns None if confidence is too low (empty, or length < 3).
    """
    if school_raw is None:
        return None
    s = str(school_raw).strip()
    if not s:
        return None
    s = _strip_leading_trailing_punctuation(s)
    s = " ".join(s.split())
    if len(s) < MIN_SCHOOL_NAME_LENGTH:
        return None
    return " ".join(word.capitalize() for word in s.split())


def _clean_school(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for key lookup."""
    txt = text.strip().lower()
    txt = txt.translate(str.maketrans("", "", string.punctuation))
    txt = " ".join(txt.split())
    return txt


def normalize_school_name(school_raw: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Normalize school name: clean OCR noise, apply known typos, casing, and map to canonical key.

    Uses sanitize_school_name (strip punctuation, trim, min length 3), optional typo correction,
    then title-case for display and SCHOOL_MAP for canonical key.

    Returns (school_norm, canonical_key). (None, None) when input is empty or < 3 chars after cleaning.
    """
    cleaned = sanitize_school_name(school_raw)
    if not cleaned:
        return None, None
    key_lower = _clean_school(cleaned)
    if key_lower in SCHOOL_TYPOS:
        key_lower = SCHOOL_TYPOS[key_lower]
    canonical = SCHOOL_MAP.get(key_lower)
    school_norm = " ".join(word.capitalize() for word in key_lower.split())
    return school_norm, canonical
