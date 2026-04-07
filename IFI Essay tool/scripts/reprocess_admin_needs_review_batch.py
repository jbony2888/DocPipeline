#!/usr/bin/env python3
"""
Reprocess a small batch (default 10) of Admin-dashboard "Needs review" submissions.

Why this exists:
- The Admin "Needs review" queue is driven by missing fields + reason codes.
- Many tickets are resolvable by re-running extraction/validation on the original PDF,
  then updating the DB with improved fields/review flags.

Safety:
- Default is DRY RUN (no writes).
- Writes require --apply.
- Updates are conservative: we only write fields that improve completeness, and we
  only clear review flags/codes when the reprocessed output indicates approval.

Requires:
- SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in `.env` (or environment)

Usage:
  python scripts/reprocess_admin_needs_review_batch.py
  python scripts/reprocess_admin_needs_review_batch.py --limit 10 --ocr-provider google
  python scripts/reprocess_admin_needs_review_batch.py --limit 10 --apply
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
    except Exception:
        pass


def _norm_str(v) -> str:
    return str(v or "").strip()


def _has_required_fields(row: dict) -> bool:
    return bool(_norm_str(row.get("student_name")) and _norm_str(row.get("school_name")) and _norm_str(row.get("grade")))


def _field_is_missing(v) -> bool:
    return not _norm_str(v)


def main() -> int:
    _load_env()

    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=10, help="How many submissions to process (default 10)")
    p.add_argument("--window", type=int, default=1000, help="Admin dashboard window size (default 1000, cap 2000)")
    p.add_argument("--ocr-provider", type=str, default="google", help="OCR provider (default google)")
    p.add_argument("--apply", action="store_true", help="Write updates to DB (default: dry run)")
    args = p.parse_args()

    limit = max(1, int(args.limit))
    window = min(max(1, int(args.window)), 2000)

    from admin.routes import _apply_school_grade_filters, _fetch_all_submissions
    from pipeline.runner import process_submission
    from pipeline.supabase_db import _get_service_role_client
    from pipeline.supabase_storage import download_original_with_service_role

    sb = _get_service_role_client()
    if not sb:
        print("ERROR: Could not create service-role Supabase client. Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        return 2

    all_rows = _fetch_all_submissions(limit=window)
    queue = _apply_school_grade_filters(all_rows, "", "", "needs_review", "")
    batch = queue[:limit]

    print(f"Admin loaded window: {len(all_rows)}")
    print(f"Admin needs_review queue (in window): {len(queue)}")
    print(f"Selected batch size: {len(batch)}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'} | ocr_provider={args.ocr_provider!r}\n")

    updated = 0
    processed = 0
    skipped_download = 0

    for row in batch:
        sid = _norm_str(row.get("submission_id"))
        filename = _norm_str(row.get("filename")) or "original.pdf"
        artifact_dir = _norm_str(row.get("artifact_dir"))

        if not sid or not artifact_dir:
            print(f"- SKIP (missing submission_id/artifact_dir): sid={sid!r}")
            continue

        original_bytes, resolved_path = download_original_with_service_role(sb, artifact_dir, filename)
        if not original_bytes:
            skipped_download += 1
            print(f"- SKIP download: {sid} file={filename!r} artifact_dir={artifact_dir!r}")
            continue

        suffix = Path(filename).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(delete=True, suffix=suffix) as tmp:
            tmp.write(original_bytes)
            tmp.flush()

            before = {
                "student_name": row.get("student_name"),
                "school_name": row.get("school_name"),
                "grade": row.get("grade"),
                "needs_review": row.get("needs_review"),
                "review_reason_codes": row.get("review_reason_codes"),
                "word_count": row.get("word_count"),
            }

            try:
                rec, _report = process_submission(
                    tmp.name,
                    submission_id=sid,
                    artifact_dir=artifact_dir,
                    ocr_provider_name=str(args.ocr_provider or "google"),
                    original_filename=filename,
                )
            except Exception as exc:
                print(f"- ERROR processing {sid}: {exc}")
                continue

            processed += 1
            after = rec.model_dump()

        # Decide what we'd update (conservative).
        updates: dict = {}
        for field in ("student_name", "school_name", "grade"):
            if _field_is_missing(before.get(field)) and not _field_is_missing(after.get(field)):
                updates[field] = after.get(field)

        # If reprocessing yields an approvable record, clear review flags/codes.
        # (This is the only time we reduce the queue automatically.)
        after_needs_review = bool(after.get("needs_review"))
        after_codes = _norm_str(after.get("review_reason_codes"))
        after_has_required = _has_required_fields(after)
        if (not after_needs_review) and after_has_required and (not after_codes):
            updates["needs_review"] = False
            updates["review_reason_codes"] = ""

        # Also refresh word_count if it was missing and we now have one.
        if before.get("word_count") in (None, "", 0) and after.get("word_count") not in (None, "", 0):
            updates["word_count"] = after.get("word_count")

        # Print a one-line summary.
        why = _norm_str(before.get("review_reason_codes"))
        why_short = why if len(why) <= 80 else why[:77] + "..."
        print(
            f"- {sid} | before: school={_norm_str(before.get('school_name')) or '(missing)'} "
            f"grade={_norm_str(before.get('grade')) or '(missing)'} "
            f"needs_review={bool(before.get('needs_review'))} reasons={why_short or '(none)'} "
            f"| downloaded_from={resolved_path or '(unknown)'}"
        )
        if not updates:
            print("    no safe updates inferred")
            continue

        print(f"    would_update: {sorted(updates.keys())}")

        if not args.apply:
            continue

        # Write using service role (bypass RLS for admin maintenance).
        resp = sb.table("submissions").update(updates).eq("submission_id", sid).execute()
        if getattr(resp, "data", None):
            updated += 1

    print("\n--- Summary ---")
    print(f"processed_ok: {processed}/{len(batch)}")
    print(f"skipped_download: {skipped_download}")
    print(f"updated: {updated}" if args.apply else "updated: (dry-run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

