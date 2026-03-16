#!/usr/bin/env python3
"""
Run the pipeline on test files without storing in the database.
Writes results to a JSON file for verifying feedback issues are fixed.

Usage:
  cd "IFI Essay tool"
  python scripts/run_feedback_verification.py [--input-dirs DIR1 DIR2 ...] [--output results.json] [--ocr-provider stub]
  python scripts/run_feedback_verification.py --input-dirs docs/typed-form-submission docs/client_test_instructions --output verification_results.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import fitz  # PyMuPDF

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT))

from pipeline.runner import process_submission
from pipeline.document_analysis import analyze_document, make_chunk_submission_id, get_batch_iter_ranges
from pipeline.schema import DocClass

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = (".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg")


def _compute_submission_id(file_path: Path) -> str:
    """Deterministic submission ID from file path and content."""
    with open(file_path, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest()
    return h[:12]


def _record_to_verification_dict(record, report: dict) -> dict:
    """Serialize record and report for JSON output."""
    data = record.model_dump() if hasattr(record, "model_dump") else record.dict()
    # Ensure doc_class is string
    dc = data.get("doc_class")
    if hasattr(dc, "value"):
        data["doc_class"] = dc.value
    # Add essay preview from report for verification
    if report.get("essay_preview"):
        data["essay_preview"] = report["essay_preview"]
    return data


def process_file(
    file_path: Path,
    ocr_provider: str,
) -> dict:
    """
    Process a single file through the pipeline (no DB, no storage).
    Returns a dict with status, records, and metadata.
    """
    result = {
        "filename": file_path.name,
        "file_path": str(file_path.resolve()),
        "status": "success",
        "error": None,
        "doc_class": None,
        "structure": None,
        "format": None,
        "chunk_count": 0,
        "records": [],
    }
    processing_path = file_path
    converted_pdf_path = None

    try:
        # Convert Word to PDF if needed
        ext = file_path.suffix.lower()
        if ext in (".doc", ".docx"):
            from pipeline.word_converter import convert_word_to_pdf
            converted_pdf_path = convert_word_to_pdf(str(file_path))
            if not converted_pdf_path:
                result["status"] = "error"
                result["error"] = "Could not convert Word to PDF"
                return result
            processing_path = Path(converted_pdf_path)

        # Analyze document
        analysis = analyze_document(str(processing_path), ocr_provider_name=ocr_provider)
        result["doc_class"] = analysis.doc_class.value if hasattr(analysis.doc_class, "value") else str(analysis.doc_class)
        result["structure"] = analysis.structure
        result["format"] = analysis.format

        # BULK_SCANNED_BATCH: use paired metadata+essay ranges; else chunk_ranges
        iter_ranges = (
            get_batch_iter_ranges(analysis)
            if analysis.doc_class == DocClass.BULK_SCANNED_BATCH
            else analysis.chunk_ranges
        )
        submission_id = _compute_submission_id(file_path)
        doc = fitz.open(str(processing_path))

        for idx, chunk in enumerate(iter_ranges):
            chunk_doc = fitz.open()
            chunk_path = None
            try:
                chunk_doc.insert_pdf(doc, from_page=chunk.start_page, to_page=chunk.end_page, widgets=0)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as chunk_file:
                    chunk_doc.save(chunk_file.name)
                    chunk_path = chunk_file.name
            finally:
                try:
                    chunk_doc.close()
                except Exception:
                    pass

            image_path = str(processing_path) if len(iter_ranges) == 1 else chunk_path
            chunk_submission_id = make_chunk_submission_id(submission_id, idx)
            artifact_dir = f"local_verification/{submission_id}/chunk_{idx}_{chunk_submission_id}"
            child_doc_class = DocClass.SINGLE_SCANNED if analysis.doc_class == DocClass.BULK_SCANNED_BATCH else analysis.doc_class

            record, report = process_submission(
                image_path=image_path,
                submission_id=chunk_submission_id,
                artifact_dir=artifact_dir,
                ocr_provider_name=ocr_provider,
                original_filename=file_path.name,
                chunk_metadata={
                    "parent_submission_id": submission_id,
                    "chunk_index": idx,
                    "chunk_page_start": chunk.start_page + 1,
                    "chunk_page_end": chunk.end_page + 1,
                    "chunk_submission_id": chunk_submission_id,
                    "is_chunk": len(iter_ranges) > 1,
                    "template_detected": analysis.structure == "template",
                    "template_blocked_low_confidence": analysis.low_confidence_for_template,
                    "doc_class": child_doc_class,
                    "analysis_structure": (
                        "single" if analysis.doc_class == DocClass.BULK_SCANNED_BATCH else analysis.structure
                    ),
                    "analysis_form_layout": analysis.form_layout,
                    "analysis_header_signature_score_max": max(
                        (p.header_signature_score for p in analysis.pages), default=0.0
                    ),
                },
                doc_format=analysis.format,
            )
            result["records"].append(_record_to_verification_dict(record, report))
            result["chunk_count"] += 1

            if chunk_path:
                try:
                    Path(chunk_path).unlink(missing_ok=True)
                except Exception:
                    pass

        doc.close()
        if converted_pdf_path:
            try:
                Path(converted_pdf_path).unlink(missing_ok=True)
            except Exception:
                pass

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        logger.warning(f"Error processing {file_path.name}: {e}")

    return result


def collect_files(input_dirs: list[Path], extensions: tuple = SUPPORTED_EXTENSIONS) -> list[Path]:
    """Collect all supported files from input directories."""
    paths = []
    for d in input_dirs:
        if not d.exists():
            logger.warning(f"Directory does not exist: {d}")
            continue
        for ext in extensions:
            paths.extend(d.rglob(f"*{ext}"))
    return sorted(set(paths))


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO_ROOT / ".env")
        load_dotenv(Path.cwd() / ".env")
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="Run pipeline on test files without database; output JSON for feedback verification."
    )
    parser.add_argument(
        "--input-dirs",
        nargs="+",
        type=Path,
        default=[
            REPO_ROOT / "docs" / "typed-form-submission",
            REPO_ROOT / "docs" / "client_test_instructions",
        ],
        help="Directories to search for PDF/DOC/DOCX files",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=REPO_ROOT / "verification_results.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--ocr-provider",
        default="stub",
        help="OCR provider: stub (offline), google (requires credentials)",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Maximum number of files to process (for quick smoke tests)",
    )
    args = parser.parse_args()

    # Resolve paths relative to REPO_ROOT
    input_dirs = [d if d.is_absolute() else REPO_ROOT / d for d in args.input_dirs]
    output_path = args.output if args.output.is_absolute() else REPO_ROOT / args.output

    files = collect_files(input_dirs)
    if args.max_files:
        files = files[: args.max_files]
    if not files:
        logger.error("No supported files found in input directories.")
        return 1

    logger.info(f"Processing {len(files)} file(s) with ocr_provider={args.ocr_provider}")
    results = []
    for fp in files:
        logger.info(f"  {fp.name}")
        r = process_file(fp, args.ocr_provider)
        results.append(r)

    summary = {
        "total_files": len(results),
        "success_count": sum(1 for r in results if r["status"] == "success"),
        "error_count": sum(1 for r in results if r["status"] == "error"),
        "total_records": sum(r["chunk_count"] for r in results),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ocr_provider": args.ocr_provider,
    }

    output = {
        "summary": summary,
        "files": results,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    logger.info(f"Results written to {output_path}")
    logger.info(f"  {summary['success_count']} files OK, {summary['error_count']} errors, {summary['total_records']} records")
    return 0 if summary["error_count"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
