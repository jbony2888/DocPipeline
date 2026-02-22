from types import SimpleNamespace
import importlib.util
from pathlib import Path

from pipeline.field_attribution import (
    assert_expected_attribution,
    build_field_attribution_debug_payload,
    compute_field_source_pages,
)
from pipeline.runner import _extract_header_fields_from_text
from pipeline.validate import validate_record
from scripts.regression_check import has_multiple_header_peaks


def _load_exported_guardrails_core():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "idp_guardrails_core"
        / "core.py"
    )
    spec = importlib.util.spec_from_file_location("idp_guardrails_core_export", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_extract_header_fields_from_text_parses_expected_labels():
    text = """Student Name: Valeria Pantoja\nSchool: Lincoln Middle School\nGrade - 8"""
    extracted = _extract_header_fields_from_text(text)

    assert extracted["student_name"] == "Valeria Pantoja"
    assert extracted["school_name"] == "Lincoln Middle School"
    assert extracted["grade"] == "8"


def test_validate_record_enforces_reason_code_invariant():
    partial = {
        "submission_id": "sub-attrib",
        "artifact_dir": "artifacts/sub-attrib",
        "student_name": "Student A",
        "school_name": "School A",
        "grade": 6,
        "word_count": 100,
        "doc_type": "ifi_typed_form_submission",
    }
    record, report = validate_record(partial)
    assert record.needs_review == (len(report["review_reason_codes"]) > 0)


def test_has_multiple_header_peaks_detects_multi_signal():
    analysis = SimpleNamespace(
        pages=[
            SimpleNamespace(header_signature_score=0.30),
            SimpleNamespace(header_signature_score=0.05),
            SimpleNamespace(header_signature_score=0.28),
            SimpleNamespace(header_signature_score=0.03),
        ]
    )
    assert has_multiple_header_peaks(analysis) is True


def test_has_multiple_header_peaks_false_with_single_peak():
    analysis = SimpleNamespace(
        pages=[
            SimpleNamespace(header_signature_score=0.30),
            SimpleNamespace(header_signature_score=0.05),
            SimpleNamespace(header_signature_score=0.10),
            SimpleNamespace(header_signature_score=0.03),
        ]
    )
    assert has_multiple_header_peaks(analysis) is False


def test_typed_form_start_page_attribution_has_no_mismatches():
    per_page_text = [
        {"page_index": 0, "text": "Student Name: Ana Perez\nSchool: Lincoln Middle School\nGrade: 8"},
        {"page_index": 1, "text": "Essay body page"},
    ]
    extracted_fields = {
        "student_name": "Ana Perez",
        "school_name": "Lincoln Middle School",
        "grade": 8,
    }
    source_pages = compute_field_source_pages(per_page_text, extracted_fields, 0, 1)
    telemetry = assert_expected_attribution(
        "ifi_typed_form_submission",
        {"chunk_page_start": 0, "chunk_page_end": 1},
        extracted_fields,
        source_pages,
    )
    assert telemetry["attribution_expected"] is True
    assert telemetry["attribution_mismatches"] == []
    assert telemetry["attribution_missing"] == []


def test_missing_attribution_builds_debug_payload():
    per_page_text = [
        {"page_index": 0, "text": "This page has no student name value"},
        {"page_index": 1, "text": "Still no matching name string"},
    ]
    extracted_fields = {
        "student_name": "Ana Perez",
        "school_name": None,
        "grade": None,
    }
    source_pages = {"student_name": None, "school_name": None, "grade": None}
    telemetry = assert_expected_attribution(
        "ifi_typed_form_submission",
        {"chunk_page_start": 0, "chunk_page_end": 1},
        extracted_fields,
        source_pages,
    )
    payload = build_field_attribution_debug_payload(
        submission_id="sub123",
        chunk_submission_id="sub123_0_x",
        doc_type="ifi_typed_form_submission",
        chunk_page_start=0,
        chunk_page_end=1,
        extracted_fields=extracted_fields,
        field_source_pages=source_pages,
        per_page_text=per_page_text,
    )
    assert payload is not None
    assert payload["chunk_submission_id"] == "sub123_0_x"
    assert payload["extracted_fields"]["student_name"] == "Ana Perez"
    assert len(telemetry["attribution_missing"]) == 1
    assert payload["missing_fields"][0]["field"] == "student_name"
    assert payload["missing_fields"][0]["pages_scanned"] == [0, 1]
    assert len(payload["missing_fields"][0]["top_candidates"]) >= 1


def test_exported_kindergarten_attribution_hardening_cases():
    core = _load_exported_guardrails_core()

    # Context match should still pass.
    result_grade_k = core.find_grade_attribution(
        [{"page_index": 0, "text": "Student header: Grade K"}], "K", 0, 0
    )
    assert result_grade_k is not None
    assert result_grade_k["page_index"] == 0
    assert result_grade_k["confidence"] == 0.9
    assert result_grade_k["method"] == "normalized_contains"

    # Standalone kindergarten should pass fallback.
    result_kindergarten = core.find_grade_attribution(
        [{"page_index": 0, "text": "Student is in Kindergarten"}], "K", 0, 0
    )
    assert result_kindergarten is not None
    assert result_kindergarten["page_index"] == 0
    assert result_kindergarten["confidence"] == 0.9
    assert result_kindergarten["method"] == "normalized_contains"

    # K-12 style phrases should not trigger fallback.
    assert (
        core.find_grade_attribution(
            [{"page_index": 0, "text": "District serves Kindergarten-12 students"}],
            "K",
            0,
            0,
        )
        is None
    )
    assert (
        core.find_grade_attribution(
            [{"page_index": 0, "text": "District serves Kindergarten 12 students"}],
            "K",
            0,
            0,
        )
        is None
    )
    assert (
        core.find_grade_attribution(
            [{"page_index": 0, "text": "District serves Kinder-12 students"}],
            "K",
            0,
            0,
        )
        is None
    )
