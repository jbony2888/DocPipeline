import fitz

from pipeline.ocr import ocr_pdf_pages
from pipeline.schema import OcrResult
from scripts.regression_check import (
    build_chunk_submission_id,
    compute_doc_reason_codes,
    extract_doc_fields_from_final_text,
)


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
