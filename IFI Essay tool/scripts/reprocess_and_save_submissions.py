#!/usr/bin/env python3
"""
Re-run the pipeline on specified submissions and save extracted values to the database.
Uses service role to update records. Values must be present in the documents.

Usage:
  python scripts/reprocess_and_save_submissions.py --submission-id 6ef20e2f2bc4
  python scripts/reprocess_and_save_submissions.py --submission-ids 6ef20e2f2bc4 e3d26aed3cf7 160dec223050
  python scripts/reprocess_and_save_submissions.py --execute  # required to actually save
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--submission-id", help="Single submission ID")
    parser.add_argument("--submission-ids", nargs="+", help="Multiple submission IDs")
    parser.add_argument("--needs-review", action="store_true", help="Process all submissions with needs_review=True")
    parser.add_argument("--exclude-grades", nargs="+", default=["8", "10"], help="Grades to skip when using --needs-review (default: 8 10)")
    parser.add_argument("--execute", action="store_true", help="Actually save to DB (default: dry run)")
    args = parser.parse_args()

    ids = []
    if args.submission_id:
        ids = [args.submission_id]
    elif args.submission_ids:
        ids = args.submission_ids
    elif args.needs_review:
        from pipeline.supabase_db import _get_service_role_client
        client = _get_service_role_client()
        if not client:
            print("❌ Could not connect to Supabase")
            return 1
        r = client.table("submissions").select("submission_id, grade").eq("needs_review", True).execute()
        rows = r.data or []
        exclude = set(str(g) for g in args.exclude_grades)
        ids = [row["submission_id"] for row in rows if str(row.get("grade") or "?") not in exclude]
        print(f"Found {len(ids)} needs_review submissions (excluding grades {exclude})")
    else:
        ids = ["6ef20e2f2bc4", "e3d26aed3cf7", "160dec223050"]

    if not ids:
        print("❌ No submission IDs provided")
        return 1

    from pipeline.runner import process_submission
    from pipeline.document_analysis import analyze_document, get_batch_iter_ranges
    from pipeline.supabase_db import _get_service_role_client
    from pipeline.supabase_storage import download_original_with_service_role

    client = _get_service_role_client()
    if not client:
        print("❌ Could not connect to Supabase")
        return 1

    mode = "dry run" if not args.execute else "SAVE"
    print(f"Mode: {mode} ({len(ids)} submission(s))")
    print()

    updated = 0
    for sid in ids:
        r = client.table("submissions").select("*").eq("submission_id", sid).execute()
        if not r.data:
            print(f"❌ {sid}: not found")
            continue
        rec = r.data[0]
        sid = rec["submission_id"]
        filename = rec["filename"]
        artifact_dir = rec.get("artifact_dir", "")

        file_bytes, _ = download_original_with_service_role(client, artifact_dir, filename)
        if not file_bytes:
            print(f"❌ {sid} ({filename}): could not download PDF")
            continue

        out_dir = PROJECT_ROOT / "debug_output" / f"reprocess_{sid}"
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = out_dir / filename
        pdf_path.write_bytes(file_bytes)

        analysis = analyze_document(str(pdf_path))
        if not analysis:
            print(f"❌ {sid}: document analysis failed")
            continue

        iter_ranges = get_batch_iter_ranges(analysis)
        if not iter_ranges:
            print(f"❌ {sid}: no chunk ranges")
            continue

        chunk = iter_ranges[0]
        record, report = process_submission(
            image_path=str(pdf_path),
            submission_id=sid,
            artifact_dir=artifact_dir,
            ocr_provider_name="google",
            original_filename=filename,
            chunk_metadata={
                "chunk_page_start": chunk.start_page + 1,
                "chunk_page_end": chunk.end_page + 1,
                "is_chunk": len(iter_ranges) > 1,
                "analysis_structure": analysis.structure,
                "analysis_form_layout": analysis.form_layout,
            },
            doc_format=analysis.format or "native_text",
            keep_artifacts_dir=str(out_dir),
        )

        updates = {
            "student_name": record.student_name,
            "school_name": record.school_name,
            "grade": record.grade,
            "word_count": record.word_count,
            "review_reason_codes": record.review_reason_codes or [],
            "needs_review": record.needs_review,
        }
        if report.get("essay_text"):
            updates["essay_text"] = report["essay_text"]

        print(f"  {sid} | {filename}")
        print(f"    Before: student={rec.get('student_name')}, school={rec.get('school_name')}, grade={rec.get('grade')}")
        print(f"    After:  student={updates['student_name']}, school={updates['school_name']}, grade={updates['grade']}")
        print(f"    word_count={updates['word_count']}, needs_review={updates['needs_review']}")

        if args.execute:
            from datetime import datetime
            updates["updated_at"] = datetime.now().isoformat()
            client.table("submissions").update(updates).eq("submission_id", sid).execute()
            updated += 1
            print(f"    ✅ Saved to DB")
        else:
            print(f"    (dry run -- use --execute to save)")

    if args.execute:
        print(f"\n✅ Updated {updated} submission(s) in DB")
    else:
        print(f"\nDry run complete. Run with --execute to save.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
