from pathlib import Path
import importlib.util


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "recover_multi_entry_parent_submissions.py"
SPEC = importlib.util.spec_from_file_location("recover_multi_entry_parent_submissions", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class DummyRecord:
    def __init__(self, **kwargs):
        self.student_name = kwargs.get("student_name")
        self.school_name = kwargs.get("school_name")
        self.grade = kwargs.get("grade")
        self.word_count = kwargs.get("word_count", 0)
        self.review_reason_codes = kwargs.get("review_reason_codes", "")


def test_is_accepted_child_requires_identity_and_word_count():
    record = DummyRecord(
        student_name="Yesenia Alvarez",
        school_name="Richard Edwards School",
        grade=4,
        word_count=180,
        review_reason_codes="",
    )
    report = {"field_attribution": {"attribution_risk_fields": []}, "doc_type": "unknown", "extracted_fields": {"student_name": "Yesenia Alvarez"}}

    accepted, reasons = MODULE._is_accepted_child(record, report)

    assert accepted is True
    assert reasons == []


def test_is_accepted_child_rejects_template_short_or_risky_records():
    record = DummyRecord(
        student_name="Yesenia Alvarez",
        school_name="Richard Edwards School",
        grade=4,
        word_count=22,
        review_reason_codes="TEMPLATE_ONLY",
    )
    report = {
        "field_attribution": {"attribution_risk_fields": ["grade"]},
        "doc_type": "template",
        "extracted_fields": {"student_name": "Yesenia Alvarez"},
    }

    accepted, reasons = MODULE._is_accepted_child(record, report)

    assert accepted is False
    assert "essay_too_short" in reasons
    assert "field_attribution_risk" in reasons
    assert any(reason.startswith("reject_codes:") for reason in reasons)
    assert "template_doc_type" in reasons


def test_existing_row_retirable_matches_broken_split_rows():
    row = {
        "student_name": "Yesenia Alvarez",
        "school_name": "",
        "grade": None,
        "word_count": 14,
        "review_reason_codes": "DOC_TYPE_UNKNOWN;SHORT_ESSAY",
    }

    assert MODULE._is_existing_row_retirable(row) is True


def test_is_accepted_child_rejects_suspicious_identity_text():
    record = DummyRecord(
        student_name="ST MARYS",
        school_name="And He Picks Me Up",
        grade=5,
        word_count=416,
        review_reason_codes="",
    )
    report = {
        "field_attribution": {"attribution_risk_fields": []},
        "doc_type": "unknown",
        "extracted_fields": {"student_name": "ST MARYS"},
    }

    accepted, reasons = MODULE._is_accepted_child(record, report)

    assert accepted is False
    assert "suspicious_identity_text" in reasons


def test_row_signature_normalizes_duplicate_variants():
    row_a = {
        "student_name": "Colt",
        "school_name": "St Mary Pontiac",
        "grade": "K",
        "word_count": 306,
    }
    row_b = {
        "student_name": " colt ",
        "school_name": "st   mary pontiac",
        "grade": "K",
        "word_count": "306",
    }

    assert MODULE._row_signature(row_a) == MODULE._row_signature(row_b)
