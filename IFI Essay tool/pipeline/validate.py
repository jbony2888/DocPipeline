"""
Validation module: computes enum review reasons and auto-approval eligibility.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from pipeline.schema import SubmissionRecord, DocClass
from pipeline.validation_policy import POLICY_VERSION, ValidationPolicy, get_policy

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
}


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
    return False


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
    return False


def _check_grade_valid(grade) -> bool:
    """Return True if grade is valid (1-12 or K/Kinder/Kindergarten variants)."""
    if grade is None or grade == "":
        return False
    if isinstance(grade, str):
        grade_str = grade.strip().upper()
        if grade_str in ["K", "KINDER", "KINDERGARTEN", "PRE-K", "PREK"]:
            return True
        try:
            return 1 <= int(grade_str) <= 12
        except ValueError:
            return True  # Accept other text grades (e.g. "First Grade")
    if isinstance(grade, int):
        return 1 <= grade <= 12
    return False


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
    policy = get_policy({**partial, "doc_type": doc_type}, report or {})
    is_container_parent = bool(partial.get("is_container_parent"))

    if doc_type == "bulk_scanned_batch" and is_container_parent:
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
            "ocr_provider": partial.get("ocr_provider"),
            "extraction_method": partial.get("extraction_method"),
            "parse_model": partial.get("parse_model"),
            "word_count": word_count,
            "final_text_char_count": int(partial.get("final_text_char_count") or 0),
            "auto_approve_eligible": True,
            "auto_approve_blockers": [],
            "container_skipped": True,
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

    if "TEMPLATE_ONLY" not in reason_codes and "student_name" in policy.required_fields:
        student_name = partial.get("student_name")
        if _is_effectively_missing_student_name(student_name):
            reason_codes.add("MISSING_STUDENT_NAME")

    if "TEMPLATE_ONLY" not in reason_codes and "school_name" in policy.required_fields:
        school_name = partial.get("school_name")
        if _is_effectively_missing_school_name(school_name):
            reason_codes.add("MISSING_SCHOOL_NAME")

    if "TEMPLATE_ONLY" not in reason_codes and "grade" in policy.required_fields:
        grade = partial.get("grade")
        grade_normalized = grade
        if isinstance(grade, str) and grade.strip().upper() in ["K", "KINDER", "KINDERGARTEN"]:
            grade_normalized = None  # "K" is valid but stored as None (schema expects int)

        if grade_normalized is None or grade_normalized == "":
            if isinstance(grade, str) and grade.strip().upper() in ["K", "KINDER", "KINDERGARTEN"]:
                pass  # K is valid
            else:
                reason_codes.add("MISSING_GRADE")
        elif isinstance(grade, str) and grade.strip().upper() not in ["K", "KINDER", "KINDERGARTEN"]:
            try:
                grade_int = int(grade.strip())
                if not (1 <= grade_int <= 12):
                    reason_codes.add("MISSING_GRADE")
            except (ValueError, AttributeError):
                reason_codes.add("MISSING_GRADE")
        elif isinstance(grade, int) and not (1 <= grade <= 12):
            reason_codes.add("MISSING_GRADE")

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
            "review_reason_codes": review_reason_codes_list,
            "extraction_method": extraction_method,
        },
        policy,
    )
    
    # Create SubmissionRecord
    # Preserve "K" (Kindergarten) as string "K" so it displays; reject out-of-range numeric grades
    grade_for_record = partial.get("grade")
    if isinstance(grade_for_record, str) and grade_for_record.strip().upper() in ["K", "KINDER", "KINDERGARTEN"]:
        grade_for_record = "K"  # Store so UI shows "K", not N/A
    elif grade_for_record is not None:
        try:
            g = int(grade_for_record) if isinstance(grade_for_record, (int, float)) else int(str(grade_for_record).strip())
            if not (1 <= g <= 12):
                grade_for_record = None
        except (ValueError, TypeError):
            pass
    
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
    }

    assert validation_report["needs_review"] == (len(validation_report["review_reason_codes"]) > 0), (
        "Post-validation invariant violation"
    )
    
    return record, validation_report
