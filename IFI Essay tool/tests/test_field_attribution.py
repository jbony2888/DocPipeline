from types import SimpleNamespace

from pipeline.runner import _extract_header_fields_from_text
from pipeline.validate import validate_record
from scripts.regression_check import has_multiple_header_peaks


def test_extract_header_fields_from_text_parses_expected_labels():
    text = """Student Name: Valeria Pantoja\nSchool: Lincoln Middle School\nGrade - 8"""
    extracted = _extract_header_fields_from_text(text)

    assert extracted["student_name"] == "Valeria Pantoja"
    assert extracted["school_name"] == "Lincoln Middle School"
    assert extracted["grade"] == "8"


def test_validate_record_flags_field_attribution_risk():
    partial = {
        "submission_id": "sub-attrib",
        "artifact_dir": "artifacts/sub-attrib",
        "student_name": "Student A",
        "school_name": "School A",
        "grade": 6,
        "word_count": 100,
        "field_attribution_risk": True,
    }
    _, report = validate_record(partial)
    assert "FIELD_ATTRIBUTION_RISK" in report["issues"]


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
