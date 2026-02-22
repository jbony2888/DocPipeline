import json

from pipeline.guardrails.attribution import compute_field_attribution_confidence
from pipeline.guardrails.doc_role import DocRole, classify_doc_role
from pipeline.guardrails.drift import build_run_snapshot, compare_snapshots
from pipeline.guardrails.reference_data import SchoolReferenceValidator
from pipeline.guardrails.validation import (
    is_name_school_possible_swap,
    normalize_grade,
)


def test_normalize_grade_kindergarten_and_numeric():
    assert normalize_grade("Kindergarten") == ("K", "kindergarten_alias")
    assert normalize_grade("10th") == (10, "ordinal")


def test_normalize_grade_invalid_range_detection():
    normalized, method = normalize_grade("Grade 40")
    assert normalized is None
    assert method == "invalid_range"


def test_school_reference_exact_and_fuzzy(tmp_path):
    csv_path = tmp_path / "schools.csv"
    csv_path.write_text("school_name\nLincoln Middle School\n", encoding="utf-8")
    validator = SchoolReferenceValidator(csv_path=str(csv_path))

    exact = validator.validate("Lincoln Middle School")
    fuzzy = validator.validate("Lincoln Middel School")
    missing = validator.validate("Unknown Academy")

    assert exact["matched"] is True and exact["method"] == "exact"
    assert fuzzy["matched"] is True and fuzzy["method"] == "fuzzy"
    assert missing["matched"] is False


def test_name_vs_school_possible_swap():
    assert is_name_school_possible_swap("Lincoln Middle School", "Lincoln Middle School") is True
    assert is_name_school_possible_swap("Ana Perez", "Lincoln Middle School") is False


def test_attribution_confidence_exact_vs_fuzzy():
    per_page = [{"page_index": 0, "text": "Student Name: Ana Perez\nSchool: Lincoln Middle School"}]
    exact = compute_field_attribution_confidence(
        per_page,
        {"student_name": "Ana Perez", "school_name": None, "grade": None},
        0,
        0,
    )
    fuzzy = compute_field_attribution_confidence(
        per_page,
        {"student_name": None, "school_name": "lincoln middle school", "grade": None},
        0,
        0,
    )
    assert exact["student_name"]["method"] == "exact_match"
    assert fuzzy["school_name"]["method"] in ("fuzzy_match", "normalized_contains")


def test_drift_snapshot_compare():
    baseline = build_run_snapshot(
        {
            "review_rate_by_doc_type": {"ifi_typed_form_submission": {"review_rate": 0.2}},
            "chunk_scoped_field_rate": 0.95,
            "chunk_scoped_field_from_start_rate": 0.95,
            "ocr_confidence_avg": 0.9,
            "reason_code_counts": {"MISSING_GRADE": 1},
        }
    )
    current = json.loads(json.dumps(baseline))
    current["chunk_scoped_field_rate"] = 0.90  # drop > 0.03
    ok, report = compare_snapshots(current, baseline)
    assert ok is False
    assert any("chunk_scoped_field_rate dropped" in issue for issue in report["issues"])


def test_classify_doc_role_container_vs_document():
    role_container = classify_doc_role(
        {"doc_class": "BULK_SCANNED_BATCH", "analysis_structure": "multi"},
        {},
        chunk_metadata=None,
    )
    role_child = classify_doc_role(
        {"doc_class": "BULK_SCANNED_BATCH", "chunk_index": 0},
        {},
        chunk_metadata={"chunk_index": 0},
    )
    assert role_container == DocRole.CONTAINER
    assert role_child == DocRole.DOCUMENT

