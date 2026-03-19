#!/usr/bin/env python3
"""
Process a single submission locally for debugging. Downloads from Supabase,
runs the pipeline, saves artifacts locally. Does NOT save to DB or storage.

Usage:
  python scripts/debug_single_submission.py "25-IFI-Essay-Form-Eng-and-Spanish-2.pdf"
  python scripts/debug_single_submission.py --submission-id f88aa17c3745
  python scripts/debug_single_submission.py --local-file /path/to/local.pdf
"""
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

OUTPUT_DIR = PROJECT_ROOT / "debug_output"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("filename", nargs="?", help="Filename to search for (e.g. 25-IFI-Essay-Form-Eng-and-Spanish-2.pdf)")
    parser.add_argument("--submission-id", help="Submission ID (overrides filename search)")
    parser.add_argument("--local-file", help="Process a local PDF file directly (no Supabase)")
    parser.add_argument("-o", "--output", default=str(OUTPUT_DIR), help="Output directory for artifacts")
    args = parser.parse_args()

    from pipeline.runner import process_submission
    from pipeline.document_analysis import analyze_document, get_batch_iter_ranges

    pdf_path = None
    sid = "local"
    filename = ""
    artifact_dir = ""

    if args.local_file:
        pdf_path = Path(args.local_file).resolve()
        if not pdf_path.exists():
            print(f"❌ File not found: {pdf_path}")
            return 1
        filename = pdf_path.name
        out_dir = Path(args.output) / "debug_local"
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"Processing local file: {pdf_path}")
    else:
        from pipeline.supabase_db import _get_service_role_client
        from pipeline.supabase_storage import download_original_with_service_role

        client = _get_service_role_client()
        if not client:
            print("❌ Could not connect to Supabase")
            return 1

        if args.submission_id:
            r = client.table("submissions").select("*").eq("submission_id", args.submission_id).execute()
        elif args.filename:
            r = client.table("submissions").select("*").ilike("filename", f"%{args.filename}%").limit(5).execute()
        else:
            print("Provide filename, --submission-id, or --local-file")
            return 1

        if not r.data:
            print("❌ No submission found")
            return 1
        rec = r.data[0]
        sid = rec["submission_id"]
        filename = rec["filename"]
        artifact_dir = rec.get("artifact_dir", "")

        print(f"Found: {sid} | {filename}")
        print(f"  DB: student={rec.get('student_name')}, school={rec.get('school_name')}, grade={rec.get('grade')}, word_count={rec.get('word_count')}")

        file_bytes, _ = download_original_with_service_role(client, artifact_dir, filename)
        if not file_bytes:
            print("❌ Could not download PDF from storage")
            return 1

        out_dir = Path(args.output) / f"debug_{sid}"
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = out_dir / filename
        pdf_path.write_bytes(file_bytes)
        print(f"  Downloaded to {pdf_path}")

    # Analyze document
    analysis = analyze_document(str(pdf_path))
    if not analysis:
        print("❌ Document analysis failed")
        return 1

    # Get first chunk range
    iter_ranges = get_batch_iter_ranges(analysis)
    if not iter_ranges:
        print("❌ No chunk ranges")
        return 1

    chunk = iter_ranges[0]
    start = chunk.start_page
    end = chunk.end_page
    doc_format = analysis.format or "native_text"

    # Run pipeline (single chunk)
    record, report = process_submission(
        image_path=str(pdf_path),
        submission_id=sid,
        artifact_dir=artifact_dir,
        ocr_provider_name="google",
        original_filename=filename,
        chunk_metadata={
            "chunk_page_start": start + 1,
            "chunk_page_end": end + 1,
            "is_chunk": len(iter_ranges) > 1,
            "analysis_structure": analysis.structure,
            "analysis_form_layout": analysis.form_layout,
        },
        doc_format=doc_format,
        keep_artifacts_dir=str(out_dir),
    )

    # Save summary
    summary = {
        "submission_id": sid,
        "filename": filename,
        "record": record.model_dump() if hasattr(record, "model_dump") else record.dict(),
        "report_stages": report.get("stages", {}),
        "extraction_debug": report.get("extraction_debug", {}),
        "essay_preview": (report.get("essay_text") or "")[:500] if report.get("essay_text") else None,
    }
    (out_dir / "debug_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("RESULTS (local only, not saved to DB)")
    print("=" * 60)
    print(f"  student_name: {record.student_name}")
    print(f"  school_name:  {record.school_name}")
    print(f"  grade:        {record.grade}")
    print(f"  word_count:   {record.word_count}")
    print(f"  needs_review: {record.needs_review}")
    print(f"  review_codes: {record.review_reason_codes}")
    print(f"\n  Artifacts saved to: {out_dir}")
    print("  - raw_text.txt, contact_block.txt, essay_block.txt")
    print("  - structured.json, validation.json, ocr.json")
    print("  - debug_summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
