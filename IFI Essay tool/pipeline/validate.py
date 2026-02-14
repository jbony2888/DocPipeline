"""
Validation module: validates extracted data and flags records needing review.
"""

from pipeline.schema import SubmissionRecord
from typing import Optional, Dict, List, Tuple


def can_approve_record(record: Dict) -> Tuple[bool, List[str]]:
    """
    Check if a record can be approved (has all required fields).
    
    Required fields for approval:
        - student_name (non-empty string)
        - school_name (non-empty string)
        - grade (non-null integer or "K")
    
    Args:
        record: Dictionary with record fields (from database or SubmissionRecord)
        
    Returns:
        Tuple of (can_approve: bool, missing_fields: List[str])
    """
    missing_fields = []
    
    # Check student_name
    student_name = record.get("student_name")
    if not student_name or not str(student_name).strip():
        missing_fields.append("student_name")
    
    # Check school_name
    school_name = record.get("school_name")
    if not school_name or not str(school_name).strip():
        missing_fields.append("school_name")
    
    # Check grade (must be non-null integer (1-12) or text like "K", "Kindergarten", etc.)
    grade = record.get("grade")
    if grade is None or grade == "":
        missing_fields.append("grade")
    elif isinstance(grade, str):
        grade_str = grade.strip().upper()
        # Accept kindergarten variants and other text grades
        if grade_str in ["K", "KINDER", "KINDERGARTEN", "PRE-K", "PREK"]:
            pass  # Valid text grade
        else:
            # Try to parse as integer
            try:
                grade_int = int(grade_str)
                if not (1 <= grade_int <= 12):
                    missing_fields.append("grade")
            except ValueError:
                # If it's not a number and not a known text grade, accept it as valid text grade
                # (e.g., "Pre-Kindergarten", "First Grade", etc.)
                pass
    elif isinstance(grade, int):
        if not (1 <= grade <= 12):
            missing_fields.append("grade")
    
    can_approve = len(missing_fields) == 0
    return can_approve, missing_fields


def validate_record(partial: dict) -> tuple[SubmissionRecord, dict]:
    """
    Validates required fields and creates SubmissionRecord.
    ALL records start with needs_review=True by default - they must be manually approved.
    
    Required fields for clean record:
        - student_name
        - school_name
        - grade
        - word_count > 0
    
    Args:
        partial: Dictionary with extracted fields and metadata
        
    Returns:
        Tuple of (SubmissionRecord, validation_report dict)
    """
    issues = []
    # ALL records start in needs_review - must be manually approved
    needs_review = True
    
    # Check required fields (student_name, school_name, grade) - missing any of these raises a flag.
    # Email and phone are extracted when available; if missing, no flag is raised.
    student_name = partial.get("student_name")
    if not student_name or not str(student_name).strip():
        issues.append("MISSING_STUDENT_NAME")
        needs_review = True
    
    school_name = partial.get("school_name")
    if not school_name or not str(school_name).strip():
        issues.append("MISSING_SCHOOL_NAME")
        needs_review = True
    
    grade = partial.get("grade")
    # Normalize grade: "K" is valid but will be stored as None in database (since grade is int)
    # For validation purposes, "K" is considered valid
    grade_normalized = grade
    if isinstance(grade, str) and grade.strip().upper() in ["K", "KINDER", "KINDERGARTEN"]:
        grade_normalized = None  # "K" is valid but stored as None (schema expects int)
    
    if grade_normalized is None or grade_normalized == "":
        # Check if it was "K" - if so, it's valid
        if isinstance(grade, str) and grade.strip().upper() in ["K", "KINDER", "KINDERGARTEN"]:
            # "K" is valid, don't flag as missing
            pass
        else:
            issues.append("MISSING_GRADE")
            needs_review = True
    elif isinstance(grade, str) and grade.strip().upper() not in ["K", "KINDER", "KINDERGARTEN"]:
        # Validate grade is 1-12 if it's a string
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

    # Check essay content with format-aware rules
    word_count = partial.get("word_count", 0)
    doc_format = partial.get("format")  # optional
    ocr_low_conf_pages = partial.get("ocr_low_conf_page_count") or 0
    ocr_min = partial.get("ocr_confidence_min")
    ocr_p10 = partial.get("ocr_confidence_p10")
    confidence = partial.get("ocr_confidence_avg")

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
    
    # Build review reason codes and embed minimal metadata for traceability
    if not issues:
        issues.append("PENDING_REVIEW")

    review_reason_codes = ";".join(issues) if issues else "PENDING_REVIEW"
    
    # Create SubmissionRecord
    # Handle "K" grade: convert to None since schema expects int
    # Reject out-of-range grades (e.g. 40, 0, 13) - treat as missing
    grade_for_record = partial.get("grade")
    if isinstance(grade_for_record, str) and grade_for_record.strip().upper() in ["K", "KINDER", "KINDERGARTEN"]:
        grade_for_record = None  # "K" stored as None (schema expects int)
    elif grade_for_record is not None:
        try:
            g = int(grade_for_record) if isinstance(grade_for_record, (int, float)) else int(str(grade_for_record).strip())
            if not (1 <= g <= 12):
                grade_for_record = None
        except (ValueError, TypeError):
            pass
    
    record = SubmissionRecord(
        submission_id=partial["submission_id"],
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
