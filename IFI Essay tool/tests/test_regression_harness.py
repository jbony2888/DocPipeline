import fitz
import json

from pipeline.ocr import ocr_pdf_pages
from pipeline.schema import OcrResult
from scripts.regression_check import (
    apply_doc_review_metrics,
    aggregate_parent_status_from_children,
    build_chunk_submission_id,
    compute_doc_reason_codes,
    enforce_attribution_thresholds,
    extract_doc_fields_from_final_text,
    write_field_attribution_debug_artifact,
)
from pipeline.guardrails.doc_role import DocRole


class SequenceOcrProvider:
    def __init__(self, texts):
        self._texts = list(texts)
        self._idx = 0

    def process_image(self, image_path: str) -> OcrResult:
        text = self._texts[self._idx]
        self._idx += 1
        return OcrResult(
            text=text,
            confidence_avg=0.9,
            confidence_min=0.9,
            confidence_p10=0.9,
            low_conf_page_count=0,
            lines=text.splitlines(),
        )


def _make_pdf(path, pages: int = 3):
    doc = fitz.open()
    for idx in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {idx} source")
    doc.save(path)
    doc.close()


def test_ocr_pdf_pages_preserves_page_index_and_distinct_text(tmp_path):
    pdf_path = tmp_path / "three_pages.pdf"
    _make_pdf(pdf_path, pages=3)

    provider = SequenceOcrProvider(["TEXT_PAGE_0", "TEXT_PAGE_1", "TEXT_PAGE_2"])
    stats, total = ocr_pdf_pages(
        str(pdf_path),
        provider_name="stub",
        provider=provider,
        include_text=True,
    )

    assert total == 3
    assert [row["page_index"] for row in stats] == [0, 1, 2]
    assert [row["text"] for row in stats] == ["TEXT_PAGE_0", "TEXT_PAGE_1", "TEXT_PAGE_2"]
    assert len({id(row) for row in stats}) == 3


def test_doc_level_aggregate_extraction_avoids_missing_flags():
    final_text = """Some intro line
School Name: Lincoln Middle School
Other header
Grade - 8
Essay body..."""

    extracted = extract_doc_fields_from_final_text(final_text)
    reason_codes, evidence = compute_doc_reason_codes(
        extracted=extracted,
        final_text=final_text,
        submission_id="sub123",
        is_template_doc=False,
        template_blocked_low_conf=False,
    )

    assert extracted["school_name"] == "Lincoln Middle School"
    assert extracted["grade"] == "8"
    assert "MISSING_SCHOOL_NAME" not in reason_codes
    assert "MISSING_GRADE" not in reason_codes
    assert evidence == {}


def test_template_short_circuit_skips_missing_field_codes():
    reason_codes, evidence = compute_doc_reason_codes(
        extracted={"grade": None, "school_name": None},
        final_text="",
        submission_id="template123",
        is_template_doc=True,
        template_blocked_low_conf=False,
    )

    assert "TEMPLATE_ONLY" in reason_codes
    assert "MISSING_SCHOOL_NAME" not in reason_codes
    assert "MISSING_GRADE" not in reason_codes
    assert evidence == {}


def test_chunk_submission_id_namespaces_by_submission_id_for_same_filename():
    filename = "same_name.pdf"
    id_a = build_chunk_submission_id("submission_A", 0, filename)
    id_b = build_chunk_submission_id("submission_B", 0, filename)

    assert id_a != id_b
    assert "submission_A" in id_a
    assert "submission_B" in id_b


def test_aggregate_parent_status_from_children_flags_parent_when_any_chunk_has_errors():
    """Regression: parent must not show clean when any chunk has errors (e.g. EMPTY_ESSAY)."""
    chunk_diagnostics = [
        {
            "chunk_index": 0,
            "chunk_needs_review": False,
            "chunk_reason_codes": [],
        },
        {
            "chunk_index": 1,
            "chunk_needs_review": True,
            "chunk_reason_codes": ["EMPTY_ESSAY"],
        },
    ]
    needs_review, reason_codes = aggregate_parent_status_from_children(chunk_diagnostics)
    assert needs_review is True
    assert "EMPTY_ESSAY" in reason_codes


def test_aggregate_parent_status_from_children_union_of_reason_codes():
    """Parent reason_codes must be union of all child reason_codes."""
    chunk_diagnostics = [
        {"chunk_index": 0, "chunk_needs_review": True, "chunk_reason_codes": ["MISSING_GRADE"]},
        {"chunk_index": 1, "chunk_needs_review": True, "chunk_reason_codes": ["EMPTY_ESSAY"]},
    ]
    needs_review, reason_codes = aggregate_parent_status_from_children(chunk_diagnostics)
    assert needs_review is True
    assert "MISSING_GRADE" in reason_codes
    assert "EMPTY_ESSAY" in reason_codes


def test_aggregate_parent_status_from_children_clean_when_all_clean():
    """Parent shows clean only when all children are clean."""
    chunk_diagnostics = [
        {"chunk_index": 0, "chunk_needs_review": False, "chunk_reason_codes": []},
        {"chunk_index": 1, "chunk_needs_review": False, "chunk_reason_codes": []},
    ]
    needs_review, reason_codes = aggregate_parent_status_from_children(chunk_diagnostics)
    assert needs_review is False
    assert len(reason_codes) == 0


def test_aggregate_parent_status_from_children_empty_returns_clean():
    """Empty chunk list returns clean (no children = no child failures)."""
    needs_review, reason_codes = aggregate_parent_status_from_children([])
    assert needs_review is False
    assert len(reason_codes) == 0


def test_enforce_attribution_thresholds_fails_below_required_rate(tmp_path):
    counts = {
        "ifi_typed_form_submission": {
            "total": 10,
            "within_chunk": 9,  # 0.90 < 0.95 threshold
            "from_start": 9,    # 0.90 < 0.95 threshold
        }
    }
    failures = enforce_attribution_thresholds(counts, tmp_path)
    assert len(failures) >= 1
    assert any("ifi_typed_form_submission" in msg for msg in failures)


def test_write_field_attribution_debug_artifact_for_missing_source(tmp_path):
    wrote = write_field_attribution_debug_artifact(
        chunk_artifact_dir=tmp_path,
        submission_id="sub1",
        chunk_submission_id="sub1_0_x",
        doc_type="ifi_typed_form_submission",
        chunk_page_start=0,
        chunk_page_end=1,
        extracted_fields={"student_name": "Ana Perez", "school_name": None, "grade": None},
        field_source_pages={"student_name": None, "school_name": None, "grade": None},
        per_page_text=[
            {"page_index": 0, "text": "No matching name here"},
            {"page_index": 1, "text": "No match either"},
        ],
    )
    assert wrote is True
    debug_path = tmp_path / "field_attribution_debug.json"
    assert debug_path.exists()
    with open(debug_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["chunk_submission_id"] == "sub1_0_x"
    assert payload["missing_fields"][0]["field"] == "student_name"


def test_apply_doc_review_metrics_excludes_container_records():
    summary = {
        "total_docs": 0,
        "docs_reviewed_count": 0,
        "auto_approved_count": 0,
        "reason_code_counts": {},
        "ocr_low_confidence_docs": 0,
        "false_empty_essay_count": 0,
        "review_rate_by_doc_type": {},
        "container_docs_count": 0,
        "skipped_container_docs": 0,
    }
    failures = []

    apply_doc_review_metrics(
        summary,
        doc_role=DocRole.CONTAINER,
        doc_type="bulk_scanned_batch",
        doc_needs_review=False,
        doc_reason_codes=set(),
        failures=failures,
        pdf_name="parent.pdf",
    )
    apply_doc_review_metrics(
        summary,
        doc_role=DocRole.DOCUMENT,
        doc_type="ifi_official_form_scanned",
        doc_needs_review=True,
        doc_reason_codes={"MISSING_GRADE"},
        failures=failures,
        pdf_name="child1.pdf",
    )
    apply_doc_review_metrics(
        summary,
        doc_role=DocRole.DOCUMENT,
        doc_type="ifi_official_form_scanned",
        doc_needs_review=False,
        doc_reason_codes=set(),
        failures=failures,
        pdf_name="child2.pdf",
    )

    assert failures == []
    assert summary["container_docs_count"] == 1
    assert summary["skipped_container_docs"] == 1
    assert summary["total_docs"] == 2
    assert summary["docs_reviewed_count"] == 1
    assert summary["auto_approved_count"] == 1
    assert summary["reason_code_counts"] == {"MISSING_GRADE": 1}
