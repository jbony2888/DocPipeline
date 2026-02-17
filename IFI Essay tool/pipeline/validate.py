"""
Validation module: validates extracted data and flags records needing review.

Uses config-driven validation rules (pipeline.validation_config). All doc types
require essay, grade, school, and student_name. Missing any required field flags
the record for human review.
"""

from pipeline.schema import SubmissionRecord, DocClass
from pipeline.validation_config import get_validation_rules
from typing import Dict, List, Tuple


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
    rules = get_validation_rules(_resolve_doc_class(record))
    missing_fields: List[str] = []

    if rules.require_student_name:
        student_name = record.get("student_name")
        if not student_name or not str(student_name).strip():
            missing_fields.append("student_name")

    if rules.require_school:
        school_name = record.get("school_name")
        if not school_name or not str(school_name).strip():
            missing_fields.append("school_name")

    if rules.require_grade:
        grade = record.get("grade")
        if not _check_grade_valid(grade):
            missing_fields.append("grade")

    return len(missing_fields) == 0, missing_fields


def validate_record(partial: dict) -> tuple[SubmissionRecord, dict]:
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
    issues: List[str] = []
    needs_review = True

    # Resolve doc_class and get validation rules (config-driven)
    doc_class_raw = partial.get("doc_class")
    doc_class = (
        DocClass(doc_class_raw)
        if isinstance(doc_class_raw, str)
        else (doc_class_raw if isinstance(doc_class_raw, DocClass) else DocClass.SINGLE_TYPED)
    )
    rules = get_validation_rules(doc_class)

    # Check required fields per config - missing any raises a flag for human review.
    # Treat form-label values (e.g. "Escuela", "Father/Father-Figure Name") as missing so we set the right reason code.
    if rules.require_student_name:
        student_name = partial.get("student_name")
        if _is_effectively_missing_student_name(student_name):
            issues.append("MISSING_STUDENT_NAME")
            needs_review = True

    if rules.require_school:
        school_name = partial.get("school_name")
        if _is_effectively_missing_school_name(school_name):
            issues.append("MISSING_SCHOOL_NAME")
            needs_review = True

    if rules.require_grade:
        grade = partial.get("grade")
        grade_normalized = grade
        if isinstance(grade, str) and grade.strip().upper() in ["K", "KINDER", "KINDERGARTEN"]:
            grade_normalized = None  # "K" is valid but stored as None (schema expects int)

        if grade_normalized is None or grade_normalized == "":
            if isinstance(grade, str) and grade.strip().upper() in ["K", "KINDER", "KINDERGARTEN"]:
                pass  # K is valid
            else:
                issues.append("MISSING_GRADE")
                needs_review = True
        elif isinstance(grade, str) and grade.strip().upper() not in ["K", "KINDER", "KINDERGARTEN"]:
            try:
                grade_int = int(grade.strip())
                if not (1 <= grade_int <= 12):
                    issues.append("MISSING_GRADE")
                    needs_review = True
            except (ValueError, AttributeError):
                issues.append("MISSING_GRADE")
                needs_review = True
        elif isinstance(grade, int) and not (1 <= grade <= 12):
            issues.append("MISSING_GRADE")
            needs_review = True

    # Template flags
    if partial.get("template_detected"):
        issues.append("TEMPLATE_ONLY")
        needs_review = True
    elif partial.get("template_blocked_low_confidence"):
        issues.append("OCR_LOW_CONFIDENCE")
        needs_review = True

    # Guardrail: fields detected only outside chunk start page can indicate cross-submission leakage.
    if partial.get("field_attribution_risk"):
        issues.append("FIELD_ATTRIBUTION_RISK")
        needs_review = True

    # Check essay content per config (format-aware rules)
    word_count = partial.get("word_count", 0)
    doc_format = partial.get("format")
    ocr_low_conf_pages = partial.get("ocr_low_conf_page_count") or 0
    ocr_min = partial.get("ocr_confidence_min")
    confidence = partial.get("ocr_confidence_avg")

    if rules.require_essay:
        if word_count == 0:
            if doc_format in ("image_only", "hybrid"):
                if (ocr_low_conf_pages and ocr_low_conf_pages > 0) or (ocr_min is not None and ocr_min < 0.5):
                    issues.append("OCR_LOW_CONFIDENCE")
                else:
                    issues.append("EMPTY_ESSAY")
            else:
                issues.append("EMPTY_ESSAY")
            needs_review = True
        elif word_count < 50:
            issues.append("SHORT_ESSAY")
            needs_review = True

    # Check OCR confidence if available (format aware)
    if confidence is not None and confidence < 0.5:
        issues.append("LOW_CONFIDENCE")
        needs_review = True
    
    # Build review reason codes: explicit reason for flag (e.g. MISSING_GRADE, MISSING_SCHOOL_NAME).
    # This value must be persisted to the DB so the UI shows the specific reason, not inferred.
    if not issues:
        issues.append("PENDING_REVIEW")
    review_reason_codes = ";".join(issues)
    
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
        "issues": issues,
        "review_reason_codes": review_reason_codes
    }
    
    return record, validation_report
