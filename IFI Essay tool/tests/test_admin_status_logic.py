"""Regression tests for shared admin submission status derivation."""

import pytest

from admin.assignments_service import derive_submission_status


def _row(**overrides):
    row = {
        "submission_id": "sub-1",
        "student_name": "Jane Student",
        "school_name": "Rachel Carson Elementary School",
        "grade": "5",
        "needs_review": False,
        "review_reason_codes": "",
        "is_container_parent": False,
        "is_blank_template": False,
        "doc_type": "",
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("row", "expected_status"),
    [
        (_row(), "approved"),
        (_row(needs_review=True), "needs_review"),
        (_row(review_reason_codes="MISSING_GRADE"), "needs_review"),
        (_row(needs_review=True, review_reason_codes=""), "needs_review"),
        (_row(review_reason_codes="EXCLUDED_FROM_REVIEW"), "excluded"),
        (_row(review_reason_codes="EXCLUDED_FROM_REVIEW;MISSING_GRADE"), "excluded"),
        (_row(is_container_parent=True, needs_review=True), "needs_review"),
        (_row(is_container_parent=True, needs_review=False, review_reason_codes="MULTI_ENTRY_PARENT"), "approved"),
        (_row(is_container_parent=True, needs_review=False), "approved"),
        (_row(is_container_parent=True, needs_review=False, school_name=""), "excluded"),
        (_row(school_name="", needs_review=False, review_reason_codes=""), "needs_review"),
    ],
)
def test_derive_submission_status_cases(row, expected_status):
    assert derive_submission_status(row) == expected_status


def test_derive_submission_status_treats_legacy_json_reason_array_as_needs_review():
    row = _row(review_reason_codes='["MISSING_GRADE"]')
    assert derive_submission_status(row) == "needs_review"


def test_derive_submission_status_requires_allowed_doc_type_when_present():
    row = _row(doc_type="ESSAY_ONLY")
    assert derive_submission_status(row) == "needs_review"
