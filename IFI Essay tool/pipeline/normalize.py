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
    if s in KINDER_TERMS:
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
    if s in KINDER_TERMS:
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


SCHOOL_MAP = {
    "rachel carson": "RACHEL_CARSON",
    "rachel carson school": "RACHEL_CARSON",
    "rachel carson elementary": "RACHEL_CARSON",
    "edwards": "EDWARDS",
    "edwards school": "EDWARDS",
}


def _clean_school(text: str) -> str:
    txt = text.strip().lower()
    txt = txt.translate(str.maketrans("", "", string.punctuation))
    txt = " ".join(txt.split())
    return txt


def normalize_school_name(school_raw: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Normalize school name casing/spacing and map to canonical key if known.
    
    Returns (school_norm, canonical_key)
    """
    if school_raw is None:
        return None, None
    cleaned = _clean_school(str(school_raw))
    if not cleaned:
        return None, None
    canonical = SCHOOL_MAP.get(cleaned)
    # Title-case for display
    school_norm = " ".join(word.capitalize() for word in cleaned.split())
    return school_norm, canonical
