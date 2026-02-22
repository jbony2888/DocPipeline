"""
Validation module: computes enum review reasons and auto-approval eligibility.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from pipeline.schema import SubmissionRecord, DocClass
from idp_guardrails_core.core import (
    ALLOWED_REASON_CODES,
    POLICY_VERSION,
    DocRole,
    SchoolReferenceValidator,
    ValidationPolicy,
    classify_doc_role,
    get_policy,
    is_grade_missing,
    is_name_school_possible_swap,
    normalize_grade,
)

_SCHOOL_REFERENCE_VALIDATOR = SchoolReferenceValidator()


def _resolve_doc_class(record: Dict) -> DocClass:
    """Resolve DocClass from record dict. Defaults to SINGLE_TYPED."""
    dc = record.get("doc_class")
    if isinstance(dc, DocClass):
        return dc
    if isinstance(dc, str):
        try:
            return DocClass(dc)
        except ValueError:
            pass
    return DocClass.SINGLE_TYPED


def _is_effectively_missing_student_name(val) -> bool:
    """True if value is missing or is a form label / placeholder (not a real name)."""
    if not val or not str(val).strip():
        return True
    s = str(val).strip()
    # Known IFI form labels or page headers mistaken for name
    if len(s) < 2:
        return True
    lower = s.lower()
    if "father/father-figure name" in lower or "nombre deo padre" in lower or "figura paterna" in lower:
        return True
    if "student's name" in lower or "nombre del estudiante" in lower:
        return True
    if s == "JUDGING PROCESS" or lower == "judging process":
        return True
    # Guardrail: avoid treating essay body text as a student's name.
    # Real names are short and typically do not contain sentence punctuation.
    token_count = len([t for t in re.split(r"\s+", s) if t])
    if len(s) > 60 or token_count > 5:
        return True
    if re.search(r"[.!?;:]", s):
        return True
    return False


def _looks_like_essay_text(s: str) -> bool:
    """
    Heuristic to detect paragraph-like text accidentally extracted into a field.
    """
    if not s:
        return False
    text = s.strip()
    if "\n" in text:
        return True
    token_count = len([t for t in re.split(r"\s+", text) if t])
    if len(text) > 80 or token_count > 8:
        return True
    if re.search(r"[.!?;:]", text):
        return True
    lower = text.lower()
    essay_markers = (
        "my father",
        "my mother",
        "another example",
        "because",
        "paragraph",
        "hard working",
    )
    return any(marker in lower for marker in essay_markers)


def _is_effectively_missing_school_name(val) -> bool:
    """True if value is missing or is only a form label (e.g. 'Escuela'), not a real school name."""
    if not val or not str(val).strip():
        return True
    s = str(val).strip()
    if len(s) < 3:
        return True
    # Label-only values from IFI form
    lower = s.lower()
    if lower in ("escuela", "/ escuela", "school", "school name"):
        return True
    if s == "Escuela" or s == "/ Escuela":
        return True
    # Guardrail: long/sentence-like content in school_name is almost always essay text.
    if _looks_like_essay_text(s):
        return True
    return False


def _check_grade_valid(grade) -> bool:
    normalized, _ = normalize_grade(grade)
    return normalized is not None


def _resolve_doc_type(partial: Dict, report: Dict | None) -> str:
    raw = (partial.get("doc_type") or "").strip()
    if not raw:
        ex_debug = (report or {}).get("extraction_debug") or {}
        ifi = ex_debug.get("ifi_classification") or {}
        raw = (ifi.get("doc_type") or "").strip()
    if not raw and partial.get("template_detected"):
        return "template"
    if not raw:
        return "unknown"
    low = raw.lower()
    mapping = {
        "ifi_typed_form_submission": "ifi_typed_form_submission",
        "ifi_official_form_scanned": "ifi_official_form_scanned",
        "ifi_official_form_filled": "ifi_official_form_filled",
        "essay_with_header_metadata": "essay_with_header_metadata",
        "standard_freeform_essay": "standard_freeform_essay",
        "bulk_scanned_batch": "bulk_scanned_batch",
        "template": "template",
        "unknown": "unknown",
        "ifi_official_template_blank": "template",
        "essay_only": "standard_freeform_essay",
    }
    return mapping.get(low, "unknown")


def _coerce_reason_codes(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str):
        raw = [s.strip() for s in value.split(";")]
    else:
        raw = [str(value).strip()]
    codes = [s for s in raw if s and s != "PENDING_REVIEW"]
    return sorted(set(codes))


def can_auto_approve(record: Dict, policy: ValidationPolicy) -> bool:
    if str(record.get("doc_role") or "").strip().lower() == DocRole.CONTAINER.value:
        return False
    codes = set(_coerce_reason_codes(record.get("review_reason_codes")))
    if codes:
        return False
    if policy.review_on_fallback_extraction and record.get("extraction_method") == "fallback":
        return False
    if "EMPTY_ESSAY" in codes or "SHORT_ESSAY" in codes:
        return False
    if "OCR_LOW_CONFIDENCE" in codes:
        return False
    return True


def can_approve_record(record: Dict) -> Tuple[bool, List[str]]:
    """
    Check if a record can be approved (has all required fields per validation config).

    Required fields for approval (config-driven; all doc types currently require all):
        - student_name (non-empty string)
        - school_name (non-empty string)
        - grade (non-null integer or "K")

    Args:
        record: Dictionary with record fields (from database or SubmissionRecord).
                May include doc_class to look up rules; otherwise SINGLE_TYPED rules apply.

    Returns:
        Tuple of (can_approve: bool, missing_fields: List[str])
    """
    doc_role = classify_doc_role(record, {}, chunk_metadata=record.get("chunk_metadata"))
    if doc_role == DocRole.CONTAINER:
        return True, []

    policy = get_policy(record, {})
    missing_fields: List[str] = []

    required_fields = policy.required_fields
    if "student_name" in required_fields:
        student_name = record.get("student_name")
        if _is_effectively_missing_student_name(student_name):
            missing_fields.append("student_name")

    if "school_name" in required_fields:
        school_name = record.get("school_name")
        if _is_effectively_missing_school_name(school_name):
            missing_fields.append("school_name")

    if "grade" in required_fields:
        grade = record.get("grade")
        if not _check_grade_valid(grade):
            missing_fields.append("grade")

    word_count = int(record.get("word_count") or 0)
    if policy.require_essay:
        if word_count == 0:
            missing_fields.append("word_count")
        elif word_count < policy.min_essay_words:
            missing_fields.append("short_essay")

    conf_avg = record.get("ocr_confidence_avg")
    if policy.min_ocr_confidence is not None and conf_avg is not None:
        try:
            if float(conf_avg) < policy.min_ocr_confidence:
                missing_fields.append("ocr_low_confidence")
        except (TypeError, ValueError):
            missing_fields.append("ocr_low_confidence")

    return len(missing_fields) == 0, missing_fields


def validate_record(partial: dict, report: dict | None = None) -> tuple[SubmissionRecord, dict]:
    """
    Validates required fields and creates SubmissionRecord.
    ALL records start with needs_review=True by default - they must be manually approved.

    Required fields are config-driven per doc_class; all doc types currently require:
        - student_name, school_name, grade, word_count > 0

    Missing any required field flags the record for human review.

    Args:
        partial: Dictionary with extracted fields and metadata (includes doc_class)

    Returns:
        Tuple of (SubmissionRecord, validation_report dict)
    """
    reason_codes: set[str] = set()

    # Resolve doc_class
    doc_class_raw = partial.get("doc_class")
    doc_class = (
        DocClass(doc_class_raw)
        if isinstance(doc_class_raw, str)
        else (doc_class_raw if isinstance(doc_class_raw, DocClass) else DocClass.SINGLE_TYPED)
    )
    doc_type = _resolve_doc_type(partial, report)
    doc_role = classify_doc_role(partial, report or {}, chunk_metadata=partial.get("chunk_metadata"))
    policy_record = {**partial, "doc_type": doc_type}
    if doc_type == "bulk_scanned_batch" and doc_role == DocRole.DOCUMENT:
        # Keep wrapper records bypassed, but validate child chunks as real documents.
        policy_record["doc_type"] = "unknown"
    policy = get_policy(policy_record, report or {})

    if doc_role == DocRole.CONTAINER:
        reason_codes = set()
        needs_review = False
        review_reason_codes_list: List[str] = []
        review_reason_codes = ""
        word_count = int(partial.get("word_count") or 0)
        confidence = partial.get("ocr_confidence_avg")
        validation_report = {
            "is_valid": True,
            "needs_review": False,
            "issues": [],
            "review_reason_codes": [],
            "review_reason_codes_db": "",
            "validation_policy_version": POLICY_VERSION,
            "policy_version": POLICY_VERSION,
            "doc_type": doc_type,
            "doc_role": doc_role.value,
            "ocr_provider": partial.get("ocr_provider"),
            "extraction_method": partial.get("extraction_method"),
            "parse_model": partial.get("parse_model"),
            "word_count": word_count,
            "final_text_char_count": int(partial.get("final_text_char_count") or 0),
            "auto_approve_eligible": False,
            "auto_approve_blockers": ["CONTAINER_RECORD"],
            "container_skipped": True,
            "validation_skipped_reason": "container_record",
        }
        record = SubmissionRecord(
            submission_id=partial["submission_id"],
            doc_class=doc_class,
            student_name=partial.get("student_name"),
            school_name=partial.get("school_name"),
            grade=partial.get("grade"),
            teacher_name=partial.get("teacher_name"),
            city_or_location=partial.get("city_or_location"),
            father_figure_name=partial.get("father_figure_name"),
            phone=partial.get("phone"),
            email=partial.get("email"),
            word_count=word_count,
            ocr_confidence_avg=confidence,
            needs_review=needs_review,
            review_reason_codes=review_reason_codes,
            artifact_dir=partial["artifact_dir"],
        )
        assert record.needs_review == (len(review_reason_codes_list) > 0)
        return record, validation_report

    # Template short-circuit
    if doc_type == "template":
        reason_codes.add("TEMPLATE_ONLY")
    else:
        if doc_type == "unknown":
            reason_codes.add("DOC_TYPE_UNKNOWN")

    # Required identity fields must be enforced for all document types.
    if "student_name" in policy.required_fields:
        student_name = partial.get("student_name")
        if _is_effectively_missing_student_name(student_name):
            reason_codes.add("MISSING_STUDENT_NAME")

    if "school_name" in policy.required_fields:
        school_name = partial.get("school_name")
        if _is_effectively_missing_school_name(school_name):
            reason_codes.add("MISSING_SCHOOL_NAME")

    grade_raw = partial.get("grade")
    grade_normalized, grade_norm_method = normalize_grade(grade_raw)
    grade_norm_telemetry = {
        "raw": grade_raw,
        "normalized": grade_normalized,
        "method": grade_norm_method,
    }
    if "grade" in policy.required_fields:
        if is_grade_missing(grade_raw):
            reason_codes.add("MISSING_GRADE")
        elif grade_normalized is None:
            reason_codes.add("INVALID_GRADE_RANGE")

    school_reference_validation = {
        "matched": False,
        "method": "skipped",
        "confidence": 0.0,
        "reference_version": _SCHOOL_REFERENCE_VALIDATOR.reference_version,
    }
    if "TEMPLATE_ONLY" not in reason_codes and "school_name" in policy.required_fields:
        school_name = partial.get("school_name")
        if not _is_effectively_missing_school_name(school_name):
            school_reference_validation = _SCHOOL_REFERENCE_VALIDATOR.validate(school_name)
            if not school_reference_validation["matched"]:
                reason_codes.add("UNKNOWN_SCHOOL")

    if "TEMPLATE_ONLY" not in reason_codes:
        if is_name_school_possible_swap(partial.get("student_name"), partial.get("school_name")):
            reason_codes.add("POSSIBLE_FIELD_SWAP")

    word_count = int(partial.get("word_count") or 0)
    doc_format = partial.get("format")
    ocr_low_conf_pages = partial.get("ocr_low_conf_page_count") or 0
    ocr_min = partial.get("ocr_confidence_min")
    confidence = partial.get("ocr_confidence_avg")
    extraction_method = (
        partial.get("extraction_method")
        or ((report or {}).get("extraction_debug") or {}).get("extraction_method")
    )

    if "TEMPLATE_ONLY" not in reason_codes:
        if policy.require_essay:
            if word_count == 0:
                reason_codes.add("EMPTY_ESSAY")
            elif 0 < word_count < policy.min_essay_words:
                reason_codes.add("SHORT_ESSAY")

        scanned_like = doc_format in ("image_only", "hybrid")
        if policy.min_ocr_confidence is not None and scanned_like:
            ocr_summary = (report or {}).get("ocr_summary") or {}
            conf_min = ocr_summary.get("confidence_min")
            if conf_min is None:
                conf_min = ocr_min
            if (ocr_low_conf_pages and ocr_low_conf_pages > 0) or (
                conf_min is not None and float(conf_min) < policy.min_ocr_confidence
            ):
                reason_codes.add("OCR_LOW_CONFIDENCE")
            elif confidence is not None and float(confidence) < policy.min_ocr_confidence:
                reason_codes.add("OCR_LOW_CONFIDENCE")

        if extraction_method == "fallback" and policy.review_on_fallback_extraction:
            reason_codes.add("EXTRACTION_FALLBACK_USED")

    # Reason codes must be enum strings only.
    reason_codes = {c for c in reason_codes if c in ALLOWED_REASON_CODES and c != "PENDING_REVIEW"}
    needs_review = len(reason_codes) > 0
    assert needs_review == (len(reason_codes) > 0), "Validation invariant violation"
    if needs_review and not reason_codes:
        raise ValueError("needs_review=True requires at least one reason code")
    if "PENDING_REVIEW" in reason_codes:
        raise ValueError("PENDING_REVIEW is forbidden")

    review_reason_codes_list = sorted(reason_codes)
    review_reason_codes = ";".join(review_reason_codes_list)
    can_auto = can_auto_approve(
        {
            **partial,
            "doc_role": doc_role.value,
            "review_reason_codes": review_reason_codes_list,
            "extraction_method": extraction_method,
        },
        policy,
    )
    
    # Create SubmissionRecord
    grade_for_record = grade_normalized
    
    record = SubmissionRecord(
        submission_id=partial["submission_id"],
        doc_class=doc_class,
        student_name=partial.get("student_name"),
        school_name=partial.get("school_name"),
        grade=grade_for_record,
        teacher_name=partial.get("teacher_name"),
        city_or_location=partial.get("city_or_location"),
        father_figure_name=partial.get("father_figure_name"),
        phone=partial.get("phone"),
        email=partial.get("email"),
        word_count=word_count,
        ocr_confidence_avg=confidence,
        needs_review=needs_review,
        review_reason_codes=review_reason_codes,
        artifact_dir=partial["artifact_dir"]
    )
    
    # Validation report
    validation_report = {
        "is_valid": not needs_review,
        "needs_review": needs_review,
        "issues": review_reason_codes_list,
        "review_reason_codes": review_reason_codes_list,
        "review_reason_codes_db": review_reason_codes,
        "validation_policy_version": POLICY_VERSION,
        "policy_version": POLICY_VERSION,
        "doc_type": doc_type,
        "doc_role": doc_role.value,
        "ocr_provider": partial.get("ocr_provider"),
        "extraction_method": extraction_method,
        "parse_model": (
            partial.get("parse_model")
            or ((report or {}).get("extraction_debug") or {}).get("model")
        ),
        "word_count": word_count,
        "final_text_char_count": int(partial.get("final_text_char_count") or 0),
        "auto_approve_eligible": can_auto,
        "auto_approve_blockers": review_reason_codes_list,
        "grade_normalization": grade_norm_telemetry,
        "school_reference_validation": school_reference_validation,
    }

    assert validation_report["needs_review"] == (len(validation_report["review_reason_codes"]) > 0), (
        "Post-validation invariant violation"
    )
    
    return record, validation_report
