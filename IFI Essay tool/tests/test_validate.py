"""
Validation tests for policy-driven review reason codes and invariants.
"""

from pipeline.validate import validate_record


def _base_partial(**overrides):
    base = {
        "submission_id": "sub_1",
        "artifact_dir": "artifacts/sub_1",
        "student_name": "Jane Doe",
        "school_name": "Rachel Carson",
        "grade": 5,
        "word_count": 120,
        "doc_type": "ifi_typed_form_submission",
        "format": "native_text",
        "ocr_confidence_avg": 0.99,
        "ocr_confidence_min": 0.98,
        "ocr_low_conf_page_count": 0,
        "extraction_method": "rule_based",
    }
    base.update(overrides)
    return base


def test_typed_form_happy_path_auto_approves():
    record, report = validate_record(_base_partial())
    assert record.needs_review is False
    assert report["review_reason_codes"] == []
    assert report["auto_approve_eligible"] is True


def test_typed_form_missing_field_flags_enum():
    record, report = validate_record(_base_partial(student_name=None))
    assert record.needs_review is True
    assert "MISSING_STUDENT_NAME" in report["review_reason_codes"]
    assert "PENDING_REVIEW" not in report["review_reason_codes"]


def test_official_scanned_missing_grade_and_school_are_flagged():
    record, report = validate_record(
        _base_partial(
            doc_type="ifi_official_form_scanned",
            format="image_only",
            grade=None,
            school_name=None,
            ocr_confidence_avg=0.85,
            ocr_confidence_min=0.75,
        )
    )
    assert "MISSING_GRADE" in report["review_reason_codes"]
    assert "MISSING_SCHOOL_NAME" in report["review_reason_codes"]
    assert record.needs_review is True
    assert report["auto_approve_eligible"] is False


def test_official_scanned_requires_essay():
    record, report = validate_record(
        _base_partial(
            doc_type="ifi_official_form_scanned",
            format="image_only",
            word_count=0,
        )
    )
    assert record.needs_review is True
    assert "EMPTY_ESSAY" in report["review_reason_codes"]


def test_ocr_low_confidence_triggers_reason_code():
    record, report = validate_record(
        _base_partial(
            doc_type="ifi_official_form_scanned",
            format="image_only",
            ocr_confidence_avg=0.40,
            ocr_confidence_min=0.30,
            ocr_low_conf_page_count=1,
        )
    )
    assert record.needs_review is True
    assert "OCR_LOW_CONFIDENCE" in report["review_reason_codes"]


def test_template_short_circuit():
    record, report = validate_record(
        _base_partial(
            doc_type="template",
            student_name=None,
            school_name=None,
            grade=None,
            word_count=0,
        )
    )
    assert record.needs_review is True
    assert "TEMPLATE_ONLY" in report["review_reason_codes"]
    assert "MISSING_STUDENT_NAME" in report["review_reason_codes"]
    assert "MISSING_SCHOOL_NAME" in report["review_reason_codes"]
    assert "MISSING_GRADE" in report["review_reason_codes"]


def test_invariant_enforced_for_needs_review_and_reason_codes():
    clean_record, clean_report = validate_record(_base_partial())
    assert clean_record.needs_review == (len(clean_report["review_reason_codes"]) > 0)
    assert "PENDING_REVIEW" not in clean_report["review_reason_codes"]

    flagged_record, flagged_report = validate_record(_base_partial(word_count=0))
    assert flagged_record.needs_review == (len(flagged_report["review_reason_codes"]) > 0)
    assert flagged_record.needs_review is True
    assert flagged_report["review_reason_codes"]
    assert "PENDING_REVIEW" not in flagged_report["review_reason_codes"]


def test_validate_typed_form_requires_fields_and_essay():
    _, report_missing_grade = validate_record(_base_partial(grade=None))
    assert "MISSING_GRADE" in report_missing_grade["review_reason_codes"]

    _, report_empty = validate_record(_base_partial(word_count=0))
    assert "EMPTY_ESSAY" in report_empty["review_reason_codes"]


def test_container_bulk_scanned_batch_skips_parent_validation():
    record, report = validate_record(
        _base_partial(
            doc_type="bulk_scanned_batch",
            is_container_parent=True,
            word_count=0,
            student_name=None,
            school_name=None,
            grade=None,
        )
    )
    assert record.needs_review is False
    assert report["review_reason_codes"] == []
    assert report["doc_role"] == "container"
    assert report["container_skipped"] is True
    assert report["validation_skipped_reason"] == "container_record"
    assert report["auto_approve_eligible"] is False
    assert report["auto_approve_blockers"] == ["CONTAINER_RECORD"]


def test_bulk_child_chunk_runs_document_validation():
    record, report = validate_record(
        _base_partial(
            doc_type="bulk_scanned_batch",
            doc_class="BULK_SCANNED_BATCH",
            chunk_index=0,
            student_name=None,
            school_name="Lincoln Elementary",
            grade=5,
        )
    )
    assert report["doc_role"] == "document"
    assert record.needs_review is True
    assert "MISSING_STUDENT_NAME" in report["review_reason_codes"]
