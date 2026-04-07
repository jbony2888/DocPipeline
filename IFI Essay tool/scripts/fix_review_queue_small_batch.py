#!/usr/bin/env python3
"""
Fix a small batch of *stale* admin "Needs review" tickets.

Background:
- The admin dashboard's "Needs review" status is computed and will include rows that
  have non-empty `review_reason_codes` even when `needs_review = false`.
- Over time, some rows end up with `needs_review=false` while `review_reason_codes`
  remains non-empty (including legacy JSON-string arrays like '["MISSING_FILE"]').

This script targets the safest win:
- Pick up to N rows from the admin dashboard "needs_review" window where:
  - needs_review == False
  - student_name, school_name, grade are present (so the row is otherwise approvable)
  - review_reason_codes is non-empty (in any format)
- Clear review_reason_codes to "" (and keep needs_review false) using service role.

Default is DRY RUN. Use --apply to write changes.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except Exception:
        pass


def _has_all_required(row: dict) -> bool:
    return bool(
        (row.get("student_name") or "").strip()
        and (row.get("school_name") or "").strip()
        and str(row.get("grade") or "").strip()
    )


def main() -> int:
    _load_env()

    p = argparse.ArgumentParser(
        description="Clear stale review_reason_codes for a small batch of admin needs_review rows."
    )
    p.add_argument("--limit", type=int, default=10, help="Max rows to update (default 10)")
    p.add_argument(
        "--window",
        type=int,
        default=1000,
        help="Admin dashboard fetch window size (default 1000, cap 2000)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Actually write updates (default is dry-run)",
    )
    args = p.parse_args()

    limit = max(1, int(args.limit))
    window = min(max(1, int(args.window)), 2000)

    # Import here so dotenv has a chance to load first.
    from admin.routes import _apply_school_grade_filters, _fetch_all_submissions
    from pipeline.metadata_essay_link import parse_reason_codes_flexible
    from pipeline.supabase_db import _get_service_role_client

    sb = _get_service_role_client()
    if not sb:
        print("ERROR: Could not create service-role Supabase client. Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        return 2

    all_rows = _fetch_all_submissions(limit=window)
    # Mirror the screenshot defaults: status=needs_review, no other filters.
    needs_review_rows = _apply_school_grade_filters(all_rows, "", "", "needs_review", "")

    candidates: list[dict] = []
    for r in needs_review_rows:
        if r.get("needs_review"):
            continue
        if not _has_all_required(r):
            continue
        raw_codes = (r.get("review_reason_codes") or "").strip()
        if not raw_codes:
            continue
        # Ensure we treat legacy JSON-string arrays as non-empty too.
        codes = parse_reason_codes_flexible(raw_codes)
        if not codes and raw_codes:
            # Unparseable but non-empty string; still counts as stale.
            codes = {"(unparseable)"}
        r["_codes"] = sorted(codes)
        candidates.append(r)

    print(f"Loaded window: {len(all_rows)} rows (admin)")
    print(f"Admin needs_review filtered: {len(needs_review_rows)} rows")
    print(f"Stale candidates (needs_review=false, has required fields, has reason codes): {len(candidates)} rows")

    # Summarize codes to confirm we're fixing the right thing.
    code_counts = Counter()
    for r in candidates:
        for c in (r.get("_codes") or []):
            code_counts[c] += 1
    if code_counts:
        print("\nTop stale codes (candidate set):")
        for code, cnt in code_counts.most_common(12):
            print(f"  {cnt:4d}  {code}")

    to_fix = candidates[:limit]
    if not to_fix:
        print("\nNothing to fix.")
        return 0

    print(f"\nWill {'APPLY' if args.apply else 'DRY-RUN'} up to {len(to_fix)} row(s):")
    for r in to_fix:
        sid = str(r.get("submission_id") or "").strip()
        fn = (r.get("filename") or "").strip()
        student = (r.get("student_name") or "").strip()
        school = (r.get("school_name") or "").strip()
        grade = str(r.get("grade") or "").strip()
        raw = (r.get("review_reason_codes") or "").strip()
        raw_short = raw if len(raw) <= 120 else raw[:117] + "..."
        print(f"- {sid} | {student} | {school} | grade={grade} | file={fn} | reasons={raw_short}")

    if not args.apply:
        print("\nDry run complete. Re-run with --apply to write changes.")
        return 0

    updated = 0
    for r in to_fix:
        sid = str(r.get("submission_id") or "").strip()
        if not sid:
            continue
        resp = (
            sb.table("submissions")
            .update({"review_reason_codes": ""})
            .eq("submission_id", sid)
            .execute()
        )
        if getattr(resp, "data", None):
            updated += 1

    print(f"\nApplied updates: {updated}/{len(to_fix)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

