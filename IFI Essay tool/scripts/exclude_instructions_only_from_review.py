#!/usr/bin/env python3
"""
Exclude all "instructions-only" submissions from the active review queue.

Definition (current):
- needs_review = true
- review_reason_codes contains TEMPLATE_ONLY (semicolon codes OR legacy JSON string)

Action:
- Add EXCLUDED_FROM_REVIEW to review_reason_codes
- Set needs_review = false

Default is DRY RUN. Use --execute to apply.
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
    p.add_argument("--limit", type=int, default=2000, help="Max rows to scan (default 2000)")
    p.add_argument("--execute", action="store_true", help="Write updates (default dry-run)")
    args = p.parse_args()

    from pipeline.supabase_db import _get_service_role_client
    from pipeline.metadata_essay_link import parse_reason_codes_flexible

    sb = _get_service_role_client()
    if not sb:
        print("❌ Could not connect to Supabase (missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY)")
        return 2

    cap = max(1, min(int(args.limit), 10000))
    rows = (
        sb.table("submissions")
        .select("submission_id, filename, created_at, needs_review, review_reason_codes, is_container_parent")
        .eq("needs_review", True)
        .order("created_at", desc=True)
        .limit(cap)
        .execute()
        .data
        or []
    )

    targets: list[dict] = []
    for r in rows:
        if r.get("is_container_parent"):
            continue
        codes = parse_reason_codes_flexible((r.get("review_reason_codes") or "").strip())
        if "TEMPLATE_ONLY" in codes:
            targets.append(r)

    print(f"Scanned needs_review rows: {len(rows)}")
    print(f"Instructions-only (TEMPLATE_ONLY) targets: {len(targets)}")

    if not targets:
        return 0

    preview = targets[:25]
    print("\nPreview (first 25):")
    for r in preview:
        print(
            f"- {r.get('submission_id')} | {r.get('filename')} | {r.get('created_at')} | reasons={r.get('review_reason_codes')}"
        )
    if len(targets) > len(preview):
        print(f"... and {len(targets) - len(preview)} more")

    if not args.execute:
        print("\nDry run complete. Re-run with --execute to apply.")
        return 0

    updated = 0
    for r in targets:
        sid = str(r.get("submission_id") or "").strip()
        if not sid:
            continue
        raw = (r.get("review_reason_codes") or "").strip()
        codes = parse_reason_codes_flexible(raw)
        codes.add("EXCLUDED_FROM_REVIEW")
        # Store as semicolon string (admin + pipeline support this format best)
        out_codes = ";".join(sorted(codes))
        resp = (
            sb.table("submissions")
            .update({"needs_review": False, "review_reason_codes": out_codes})
            .eq("submission_id", sid)
            .execute()
        )
        if getattr(resp, "data", None):
            updated += 1

    print(f"\n✅ Excluded {updated}/{len(targets)} instruction-only submission(s) from review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

