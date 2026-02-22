"""
Validation policy matrix by IFI document type.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Set

POLICY_VERSION = "v1"


@dataclass(frozen=True)
class ValidationPolicy:
    required_fields: Set[str]
    min_essay_words: int
    require_essay: bool
    min_ocr_confidence: float | None
    review_on_fallback_extraction: bool


_POLICIES: Dict[str, ValidationPolicy] = {
    "ifi_typed_form_submission": ValidationPolicy(
        required_fields={"student_name", "grade", "school_name"},
        min_essay_words=50,
        require_essay=True,
        min_ocr_confidence=None,
        review_on_fallback_extraction=True,
    ),
    "ifi_official_form_scanned": ValidationPolicy(
        required_fields={"student_name"},
        min_essay_words=50,
        require_essay=True,
        min_ocr_confidence=0.50,
        review_on_fallback_extraction=True,
    ),
    "ifi_official_form_filled": ValidationPolicy(
        required_fields={"student_name"},
        min_essay_words=50,
        require_essay=True,
        min_ocr_confidence=None,
        review_on_fallback_extraction=True,
    ),
    "essay_with_header_metadata": ValidationPolicy(
        required_fields={"student_name"},
        min_essay_words=50,
        require_essay=True,
        min_ocr_confidence=None,
        review_on_fallback_extraction=True,
    ),
    "standard_freeform_essay": ValidationPolicy(
        required_fields=set(),
        min_essay_words=50,
        require_essay=True,
        min_ocr_confidence=None,
        review_on_fallback_extraction=False,
    ),
    "bulk_scanned_batch": ValidationPolicy(
        required_fields=set(),
        min_essay_words=0,
        require_essay=False,
        min_ocr_confidence=None,
        review_on_fallback_extraction=False,
    ),
    "template": ValidationPolicy(
        required_fields=set(),
        min_essay_words=0,
        require_essay=False,
        min_ocr_confidence=None,
        review_on_fallback_extraction=False,
    ),
    "unknown": ValidationPolicy(
        required_fields={"student_name"},
        min_essay_words=50,
        require_essay=True,
        min_ocr_confidence=None,
        review_on_fallback_extraction=True,
    ),
}


def _normalize_doc_type(record: dict, report: dict) -> str:
    legacy = (record.get("doc_type") or "").strip()
    if not legacy:
        ex_debug = (report or {}).get("extraction_debug") or {}
        ifi = ex_debug.get("ifi_classification") or {}
        legacy = (ifi.get("doc_type") or "").strip()
    if not legacy and record.get("template_detected"):
        return "template"
    if not legacy:
        return "unknown"

    low = legacy.lower()
    legacy_map = {
        "ifi_typed_form_submission": "ifi_typed_form_submission",
        "ifi_official_form_scanned": "ifi_official_form_scanned",
        "ifi_official_form_filled": "ifi_official_form_filled",
        "essay_with_header_metadata": "essay_with_header_metadata",
        "standard_freeform_essay": "standard_freeform_essay",
        "bulk_scanned_batch": "bulk_scanned_batch",
        "template": "template",
        "unknown": "unknown",
        # Legacy uppercase aliases from extractor
        "ifi_official_template_blank": "template",
        "ifi_official_form_filled": "ifi_official_form_filled",
        "essay_only": "standard_freeform_essay",
    }
    return legacy_map.get(low, "unknown")


def get_policy(record: dict, report: dict) -> ValidationPolicy:
    """
    Resolve validation policy for the current record/report context.
    """
    doc_type = _normalize_doc_type(record or {}, report or {})
    base = _POLICIES.get(doc_type, _POLICIES["unknown"])
    # Unknown gets OCR floor only for scanned/hybrid inputs.
    if doc_type == "unknown":
        doc_format = (record.get("format") or "").strip().lower()
        if doc_format in ("image_only", "hybrid"):
            return replace(base, min_ocr_confidence=0.50)
    return base

