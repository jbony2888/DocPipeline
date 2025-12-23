"""
Validation module: validates extracted data and flags records needing review.
"""

from pipeline.schema import SubmissionRecord
from typing import Optional


def validate_record(partial: dict) -> tuple[SubmissionRecord, dict]:
    """
    Validates required fields and creates SubmissionRecord.
    Sets needs_review flag and reason codes for incomplete records.
    
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
    needs_review = False
    
    # Check required fields
    if not partial.get("student_name"):
        issues.append("MISSING_NAME")
        needs_review = True
    
    if not partial.get("school_name"):
        issues.append("MISSING_SCHOOL")
        needs_review = True
    
    if not partial.get("grade"):
        issues.append("MISSING_GRADE")
        needs_review = True
    
    # Check essay content
    word_count = partial.get("word_count", 0)
    if word_count == 0:
        issues.append("EMPTY_ESSAY")
        needs_review = True
    elif word_count < 50:
        issues.append("SHORT_ESSAY")
        needs_review = True
    
    # Check OCR confidence if available
    confidence = partial.get("ocr_confidence_avg")
    if confidence and confidence < 0.5:
        issues.append("LOW_CONFIDENCE")
        needs_review = True
    
    # Build review reason codes
    review_reason_codes = ";".join(issues) if issues else ""
    
    # Create SubmissionRecord
    record = SubmissionRecord(
        submission_id=partial["submission_id"],
        student_name=partial.get("student_name"),
        school_name=partial.get("school_name"),
        grade=partial.get("grade"),
        teacher_name=partial.get("teacher_name"),
        city_or_location=partial.get("city_or_location"),
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

