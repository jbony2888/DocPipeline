"""
Shared enum-like reason-code definitions for deterministic validation.
"""

ALLOWED_REASON_CODES = {
    "MISSING_STUDENT_NAME",
    "MISSING_GRADE",
    "MISSING_SCHOOL_NAME",
    "EMPTY_ESSAY",
    "SHORT_ESSAY",
    "OCR_LOW_CONFIDENCE",
    "EXTRACTION_FALLBACK_USED",
    "TEMPLATE_ONLY",
    "DOC_TYPE_UNKNOWN",
    "INVALID_GRADE_RANGE",
    "UNKNOWN_SCHOOL",
    "POSSIBLE_FIELD_SWAP",
}

