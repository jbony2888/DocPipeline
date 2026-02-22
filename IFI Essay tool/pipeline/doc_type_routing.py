"""
Deterministic doc_type routing for validation policy selection.
"""

from __future__ import annotations

from typing import Any

import fitz

IFI_ANCHORS = (
    "ifi fatherhood essay contest",
    "illinois fatherhood initiative",
    "father/father-figure",
    "nombre del estudiante",
    "student's name",
)


def detect_pdf_has_acroform_fields(pdf_path: str) -> bool:
    """
    Return True when the PDF appears to contain AcroForm widgets.
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return False
    try:
        for page in doc:
            try:
                widgets = page.widgets()
                if widgets and any(True for _ in widgets):
                    return True
            except Exception:
                continue
            # Fallback: some text-layer extraction outputs explicit form-field markers.
            try:
                page_text = page.get_text("text") or ""
            except Exception:
                page_text = ""
            if "[FORM FIELD]" in page_text:
                return True
        return False
    finally:
        try:
            doc.close()
        except Exception:
            pass


def _get_analysis_value(analysis: Any, key: str, default=None):
    if isinstance(analysis, dict):
        return analysis.get(key, default)
    return getattr(analysis, key, default)


def _looks_freeform_native_text(text_layer: str | None) -> bool:
    text = (text_layer or "").lower()
    if not text.strip():
        return False
    return not any(anchor in text for anchor in IFI_ANCHORS)


def _has_high_header_signature(analysis: Any) -> bool:
    pages = _get_analysis_value(analysis, "pages", []) or []
    max_score = 0.0
    for p in pages:
        score = p.get("header_signature_score", 0.0) if isinstance(p, dict) else getattr(
            p, "header_signature_score", 0.0
        )
        if score is not None:
            max_score = max(max_score, float(score))
    explicit = _get_analysis_value(analysis, "header_signature_score", None)
    if explicit is not None:
        max_score = max(max_score, float(explicit))
    return max_score >= 0.2


def route_doc_type(analysis: Any, text_layer: str | None, has_acroform: bool) -> str:
    """
    Route canonical lowercase doc_type using deterministic priority.
    """
    if has_acroform:
        return "ifi_typed_form_submission"

    structure = (_get_analysis_value(analysis, "structure", "") or "").strip()
    doc_format = (_get_analysis_value(analysis, "format", "") or "").strip()
    form_layout = (_get_analysis_value(analysis, "form_layout", "") or "").strip()

    if structure == "template":
        return "template"

    if structure == "multi" and doc_format in ("image_only", "hybrid"):
        return "bulk_scanned_batch"

    if form_layout == "ifi_official_scanned" or (
        doc_format in ("image_only", "hybrid") and _has_high_header_signature(analysis)
    ):
        return "ifi_official_form_scanned"

    if form_layout == "ifi_official_typed":
        return "ifi_official_form_filled"

    if doc_format == "native_text" and _looks_freeform_native_text(text_layer):
        return "standard_freeform_essay"

    return "unknown"

