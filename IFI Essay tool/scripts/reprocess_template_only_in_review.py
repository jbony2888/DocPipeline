#!/usr/bin/env python3
"""
Reprocess ONLY submissions that are currently in review and marked TEMPLATE_ONLY.

This is meant to clean up "instructions-only/template" rows that accidentally landed
in the review queue (or have stale counts/flags).

Selection:
- needs_review = true
- review_reason_codes contains TEMPLATE_ONLY (semicolon codes OR legacy JSON string)

Default is DRY RUN. Use --execute to persist updates.
"""

from __future__ import annotations

import argparse
import sys
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


def main() -> int:
    _load_env()

    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=50, help="Max rows to reprocess (default 50)")
    p.add_argument("--ocr-provider", default="google", help="OCR provider (default google)")
    p.add_argument("--execute", action="store_true", help="Write updates to DB (default dry-run)")
    args = p.parse_args()

    limit = max(1, min(int(args.limit), 500))

    from pipeline.supabase_db import _get_service_role_client
    from pipeline.metadata_essay_link import parse_reason_codes_flexible

    sb = _get_service_role_client()
    if not sb:
        print("❌ Could not connect to Supabase (missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY)")
        return 2

    # Pull candidates. (Supabase Python client doesn't have robust contains/like for this field
    # across both semicolon and legacy JSON formats, so we filter client-side.)
    rows = (
        sb.table("submissions")
        .select("submission_id, filename, needs_review, review_reason_codes, created_at, is_container_parent")
        .eq("needs_review", True)
        .order("created_at", desc=True)
        .limit(2000)
        .execute()
        .data
        or []
    )

    ids: list[str] = []
    for r in rows:
        if r.get("is_container_parent"):
            continue
        codes = parse_reason_codes_flexible((r.get("review_reason_codes") or "").strip())
        if "TEMPLATE_ONLY" in codes:
            sid = str(r.get("submission_id") or "").strip()
            if sid:
                ids.append(sid)
        if len(ids) >= limit:
            break

    ids = list(dict.fromkeys(ids))
    if not ids:
        print("No needs_review TEMPLATE_ONLY submissions found.")
        return 0

    mode = "EXECUTE" if args.execute else "dry run"
    print(f"Mode: {mode} ({len(ids)} submission(s))")
    print("Submission IDs:")
    for sid in ids:
        print(" ", sid)

    # Reuse the existing reprocess script logic to avoid duplicating update semantics.
    from scripts.reprocess_and_save_submissions import main as reprocess_main

    argv_backup = list(sys.argv)
    try:
        sys.argv = [
            argv_backup[0],
            "--submission-ids",
            *ids,
            "--ocr-provider",
            str(args.ocr_provider),
        ]
        if args.execute:
            sys.argv.append("--execute")
        reprocess_main()
    finally:
        sys.argv = argv_backup

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

