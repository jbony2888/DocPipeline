#!/usr/bin/env python3
"""
Re-run the pipeline on specified submissions and save extracted values to the database.
Uses service role to update records. Values must be present in the documents.

Use --full-pdf for multi-page scans where page 1 is the IFI form and pages 2+ are the essay
(one submission_id, whole file processed; applies multipage form+essay segmentation).

Usage:
  python scripts/reprocess_and_save_submissions.py --submission-id 6ef20e2f2bc4
  python scripts/reprocess_and_save_submissions.py --submission-ids 6ef20e2f2bc4 e3d26aed3cf7 160dec223050
  # One PDF = page 1 IFI form + pages 2+ essay (no parent/chunk rows): use --full-pdf
  python scripts/reprocess_and_save_submissions.py --filename-ilike "%Edwards%Balcazar%" --full-pdf --execute
  # Multi-entry chunk children (parent_submission_id set): whole stored chunk PDF is processed automatically
  python scripts/reprocess_and_save_submissions.py --submission-id <child_id> --execute
  python scripts/reprocess_and_save_submissions.py --short-essay-candidates --full-pdf --limit 100 --execute
  # All grade 1 rows (after multi-entry split, refreshes chunk PDFs + standalone)
  python scripts/reprocess_and_save_submissions.py --grade 1 --limit 800 --execute
  python scripts/reprocess_and_save_submissions.py --grade 1 --execute --abort-on-duplicate-filename  # fail if shared filenames
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
    parser.add_argument("--filenames", nargs="+", help="Exact filename(s): all matching submission rows are reprocessed")
    parser.add_argument(
        "--filename-ilike",
        type=str,
        default=None,
        help="SQL ilike pattern (e.g. %%Edwards%%Balcazar%%) to match filenames",
    )
    parser.add_argument(
        "--short-essay-candidates",
        action="store_true",
        help="Select rows with word_count < 50 (likely missing essay from multipage scans)",
    )
    parser.add_argument("--limit", type=int, default=200, help="Max rows for --grade / --short-essay-candidates / --filename-ilike")
    parser.add_argument(
        "--grade",
        type=str,
        default=None,
        help="Select all non-container submissions with this grade (e.g. 1). Matches string or int in DB.",
    )
    parser.add_argument("--needs-review", action="store_true", help="Process all submissions with needs_review=True")
    parser.add_argument("--exclude-grades", nargs="+", default=["8", "10"], help="Grades to skip when using --needs-review (default: 8 10)")
    parser.add_argument(
        "--full-pdf",
        action="store_true",
        help="Process entire PDF as one submission (no analysis chunk slice). Use for form page 1 + essay pages 2+.",
    )
    parser.add_argument(
        "--ocr-provider",
        default="google",
        help="OCR provider for pipeline (default: google). Use stub for fast local smoke tests only.",
    )
    parser.add_argument("--execute", action="store_true", help="Actually save to DB (default: dry run)")
    parser.add_argument(
        "--abort-on-duplicate-filename",
        action="store_true",
        help="Exit with error if any selected row shares its filename with another submission (avoids bulk OCR mix-ups).",
    )
    args = parser.parse_args()

    from pipeline.supabase_db import _get_service_role_client

    client = _get_service_role_client()
    if not client:
        print("❌ Could not connect to Supabase")
        return 1

    ids: list[str] = []
    if args.submission_id:
        ids = [args.submission_id]
    elif args.submission_ids:
        ids = list(args.submission_ids)
    elif args.filenames:
        for fn in args.filenames:
            fn = (fn or "").strip()
            if not fn:
                continue
            r = client.table("submissions").select("submission_id").eq("filename", fn).execute()
            for row in r.data or []:
                ids.append(row["submission_id"])
        ids = list(dict.fromkeys(ids))
        print(f"Resolved {len(ids)} submission(s) from --filenames")
    elif args.filename_ilike:
        pat = args.filename_ilike.strip()
        if not pat:
            print("❌ Empty --filename-ilike")
            return 1
        r = (
            client.table("submissions")
            .select("submission_id, filename")
            .ilike("filename", pat)
            .limit(max(1, int(args.limit)))
            .execute()
        )
        for row in r.data or []:
            ids.append(row["submission_id"])
        ids = list(dict.fromkeys(ids))
        print(f"Found {len(ids)} submission(s) matching filename ilike {pat!r}")
    elif args.short_essay_candidates:
        cap = max(1, min(int(args.limit), 2000))
        r = (
            client.table("submissions")
            .select("submission_id, filename, word_count")
            .lt("word_count", 50)
            .eq("is_container_parent", False)
            .limit(cap)
            .execute()
        )
        for row in r.data or []:
            ids.append(row["submission_id"])
        ids = list(dict.fromkeys(ids))
        print(f"Found {len(ids)} submission(s) with word_count < 50 (limit {cap})")
    elif args.needs_review:
        r = client.table("submissions").select("submission_id, grade").eq("needs_review", True).execute()
        rows = r.data or []
        exclude = set(str(g) for g in args.exclude_grades)
        ids = [row["submission_id"] for row in rows if str(row.get("grade") or "?") not in exclude]
        print(f"Found {len(ids)} needs_review submissions (excluding grades {exclude})")
    elif args.grade is not None:
        cap = max(1, min(int(args.limit), 2000))
        g = str(args.grade).strip()
        vals = [g]
        if g.isdigit():
            vals.append(int(g))
        seen: set[str] = set()
        ids = []
        for val in vals:
            r = (
                client.table("submissions")
                .select("submission_id")
                .eq("is_container_parent", False)
                .eq("grade", val)
                .limit(cap)
                .execute()
            )
            for row in r.data or []:
                sid = row["submission_id"]
                if sid not in seen:
                    seen.add(sid)
                    ids.append(sid)
            if len(ids) >= cap:
                break
        ids = ids[:cap]
        print(f"Found {len(ids)} submission(s) with grade={g!r} (limit {cap})")
    else:
        ids = ["6ef20e2f2bc4", "e3d26aed3cf7", "160dec223050"]

    if not ids:
        print("❌ No submission IDs provided")
        return 1

    def _chunks(lst: list, n: int):
        for i in range(0, len(lst), n):
            yield lst[i : i + n]

    def _report_duplicate_filenames_in_selection(sb, submission_ids: list[str]) -> tuple[list[dict], int]:
        """Return (detail rows where filename appears >1 in DB), count of risky rows in selection."""
        sid_to_meta: dict[str, tuple[str, bool]] = {}
        for batch in _chunks(submission_ids, 100):
            r = (
                sb.table("submissions")
                .select("submission_id, filename, parent_submission_id")
                .in_("submission_id", batch)
                .execute()
            )
            for row in r.data or []:
                sid = row.get("submission_id")
                fn = (row.get("filename") or "").strip()
                sid_to_meta[sid] = (fn, bool(row.get("parent_submission_id")))
        unique_fns = {sid_to_meta[s][0] for s in submission_ids if s in sid_to_meta and sid_to_meta[s][0]}
        fn_count: dict[str, int] = {}
        for fn in unique_fns:
            r = (
                sb.table("submissions")
                .select("submission_id", count="exact")
                .eq("filename", fn)
                .execute()
            )
            fn_count[fn] = int(getattr(r, "count", None) or len(r.data or []))
        details: list[dict] = []
        for sid in submission_ids:
            if sid not in sid_to_meta:
                continue
            fn, has_parent = sid_to_meta[sid]
            if not fn:
                continue
            n = fn_count.get(fn, 1)
            if n > 1:
                details.append(
                    {
                        "submission_id": sid,
                        "filename": fn,
                        "rows_with_same_filename_in_db": n,
                        "chunk_child": has_parent,
                    }
                )
        return details, len(details)

    dup_details, dup_n = _report_duplicate_filenames_in_selection(client, ids)
    if dup_n:
        print(
            f"⚠️  {dup_n} of {len(ids)} selected row(s) share a filename with at least one other submission "
            "(same display name, different rows)."
        )
        for d in dup_details[:20]:
            print(
                f"    {d['submission_id']} | {d['filename']!r} | {d['rows_with_same_filename_in_db']} rows | "
                f"chunk_child={d['chunk_child']}"
            )
        if dup_n > 20:
            print(f"    ... and {dup_n - 20} more")
        print("    Tip: run python scripts/analyze_duplicate_filename_submissions.py")
        if args.abort_on_duplicate_filename:
            print("❌ Stopping (--abort-on-duplicate-filename). Re-run with explicit --submission-id list or fix data.")
            return 2
        print()
    elif args.abort_on_duplicate_filename:
        print("✓ No duplicate-filename risk in this selection (--abort-on-duplicate-filename ok).")
        print()

    from pipeline.runner import process_submission
    from pipeline.document_analysis import analyze_document, get_batch_iter_ranges
    from pipeline.supabase_storage import download_original_with_service_role
    from pipeline.schema import DocClass

    def _doc_class_from_row(val) -> DocClass | None:
        if val is None:
            return None
        if isinstance(val, DocClass):
            return val
        s = str(val).strip()
        for dc in DocClass:
            if dc.value == s or dc.name == s:
                return dc
        return None

    mode = "dry run" if not args.execute else "SAVE"
    print(f"Mode: {mode} ({len(ids)} submission(s))")
    if len(ids) > 1 and (args.filenames or args.filename_ilike):
        print(
            "⚠️  Multiple rows matched: each submission_id is updated from its own artifact_dir. "
            "If many rows share the same filename, confirm each row points to the correct upload."
        )
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

        if rec.get("is_container_parent"):
            print(f"⏭️  {sid} ({filename}): skip container parent row")
            continue

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

        parent_id = rec.get("parent_submission_id")
        db_chunk_start = rec.get("chunk_page_start")
        db_chunk_end = rec.get("chunk_page_end")
        is_stored_chunk = bool(parent_id) or (
            db_chunk_start is not None and db_chunk_end is not None
        )

        if args.full_pdf:
            record, report = process_submission(
                image_path=str(pdf_path),
                submission_id=sid,
                artifact_dir=artifact_dir,
                ocr_provider_name=args.ocr_provider,
                original_filename=filename,
                chunk_metadata=None,
                doc_format=analysis.format or "native_text",
                keep_artifacts_dir=str(out_dir),
            )
        elif is_stored_chunk:
            # Storage holds the per-student chunk PDF (or equivalent); process the whole file.
            # Do not take iter_ranges[0] from analysis of the chunk — that often drops essay pages.
            dc = _doc_class_from_row(rec.get("doc_class"))
            record, report = process_submission(
                image_path=str(pdf_path),
                submission_id=sid,
                artifact_dir=artifact_dir,
                ocr_provider_name=args.ocr_provider,
                original_filename=filename,
                chunk_metadata={
                    "parent_submission_id": parent_id,
                    "chunk_index": rec.get("chunk_index"),
                    "chunk_page_start": db_chunk_start,
                    "chunk_page_end": db_chunk_end,
                    "is_chunk": True,
                    "doc_class": dc,
                    "analysis_structure": analysis.structure,
                    "analysis_form_layout": analysis.form_layout,
                    "analysis_header_signature_score_max": max(
                        (p.header_signature_score for p in analysis.pages),
                        default=0.0,
                    ),
                },
                doc_format=analysis.format or "native_text",
                keep_artifacts_dir=str(out_dir),
            )
        else:
            iter_ranges = get_batch_iter_ranges(analysis)
            if not iter_ranges:
                print(f"❌ {sid}: no chunk ranges")
                continue

            chunk = iter_ranges[0]
            record, report = process_submission(
                image_path=str(pdf_path),
                submission_id=sid,
                artifact_dir=artifact_dir,
                ocr_provider_name=args.ocr_provider,
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

        rr = record.review_reason_codes
        if rr is None:
            rr = ""
        elif not isinstance(rr, str):
            rr = str(rr)

        updates = {
            "student_name": record.student_name,
            "school_name": record.school_name,
            "grade": record.grade,
            "word_count": record.word_count,
            "review_reason_codes": rr,
            "needs_review": record.needs_review,
            "ocr_confidence_avg": record.ocr_confidence_avg,
        }
        if hasattr(record.doc_class, "value"):
            updates["doc_class"] = record.doc_class.value
        elif record.doc_class is not None:
            updates["doc_class"] = str(record.doc_class)
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
