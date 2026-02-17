"""
Tests for standard freeform essay PDFs (typed, not official IFI form).

These PDFs have extractable text; the pipeline uses:
- PDF text layer extraction (no OCR)
- Groq LLM for data normalization (student_name, school_name, grade, essay)

Run with GROQ_API_KEY set for full normalization; without it, rule-based fallback is used.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except Exception:
    pass

STANDARD_FREEFORM_ESSAY_DIR = REPO_ROOT / "docs" / "standard_freeform_essay"


def _get_standard_freeform_pdfs():
    """Discover all PDFs in docs/standard_freeform_essay."""
    if not STANDARD_FREEFORM_ESSAY_DIR.is_dir():
        return []
    return sorted(STANDARD_FREEFORM_ESSAY_DIR.glob("*.pdf"))


@pytest.fixture(scope="module")
def standard_freeform_pdf_paths():
    """List of PDF paths in docs/standard_freeform_essay (empty if folder missing)."""
    return _get_standard_freeform_pdfs()


class TestStandardFreeformEssayPipeline:
    """Run full pipeline on typed freeform essay PDFs: text extraction + Groq normalization."""

    @pytest.mark.skipif(
        not _get_standard_freeform_pdfs(),
        reason="docs/standard_freeform_essay has no PDFs",
    )
    def test_standard_freeform_essay_folder_has_pdfs(self, standard_freeform_pdf_paths):
        """At least one PDF exists in the standard freeform essay folder."""
        assert len(standard_freeform_pdf_paths) >= 1

    @pytest.mark.parametrize("pdf_path", _get_standard_freeform_pdfs(), ids=lambda p: p.name)
    def test_each_freeform_pdf_processes_without_error(
        self,
        pdf_path: Path,
    ):
        """Each PDF in standard_freeform_essay runs through the pipeline without raising."""
        from pipeline.document_analysis import analyze_document
        from pipeline.runner import process_submission

        analysis = analyze_document(str(pdf_path), ocr_provider_name="stub")
        # Single-doc typed PDFs: one chunk
        assert analysis.chunk_ranges, f"Expected at least one chunk for {pdf_path.name}"

        chunk = analysis.chunk_ranges[0]
        # Process as single chunk (full doc)
        record, report = process_submission(
            image_path=str(pdf_path),
            submission_id=f"test_freeform_{pdf_path.stem}",
            artifact_dir=f"local/test_freeform/{pdf_path.stem}",
            ocr_provider_name="stub",
            original_filename=pdf_path.name,
            chunk_metadata={
                "is_chunk": True,
                "chunk_index": 0,
                "chunk_page_start": chunk.start_page,
                "chunk_page_end": chunk.end_page,
                "doc_class": analysis.doc_class,
            },
            doc_format=analysis.format,
        )

        assert record is not None, f"process_submission returned no record for {pdf_path.name}"
        assert record.submission_id
        # Typed PDFs: text from layer + Groq normalization. We expect at least essay content (word_count) or metadata.
        extracted = report.get("extracted_fields", {})
        has_metadata = any(
            extracted.get(k) for k in ("student_name", "school_name", "grade")
        )
        has_essay = getattr(record, "word_count", 0) > 0
        assert has_essay or has_metadata, (
            f"Expected word_count>0 or at least one of student_name/school_name/grade for {pdf_path.name}; "
            f"word_count={getattr(record, 'word_count', None)} extracted={extracted}"
        )
