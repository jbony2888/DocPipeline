#!/usr/bin/env python3
"""
Analyze submission failure reasons from Supabase (service role).

Usage (from IFI Essay tool directory, with .env loaded):
  python scripts/analyze_submission_failures.py
  python scripts/analyze_submission_failures.py --limit 5000

Prints: needs_review vs approved, rows missing reason codes, per-code counts,
and top duplicate filenames (signals re-runs / chunk duplicates).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

# Repo root = parent of scripts/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from pipeline.supabase_db import _get_service_role_client
from pipeline.validate import ALLOWED_REASON_CODES


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=2000, help="Max rows to fetch (default 2000, cap 10000)")
    args = p.parse_args()
    cap = min(max(args.limit, 1), 10000)

    sb = _get_service_role_client()
    if not sb:
        print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        sys.exit(1)

    result = (
        sb.table("submissions")
        .select(
            "submission_id, filename, needs_review, review_reason_codes, created_at, student_name, school_name"
        )
        .order("created_at", desc=True)
        .limit(cap)
        .execute()
    )
    rows = result.data or []

    needs = 0
    appr = 0
    no_code = 0
    code_counts: Counter[str] = Counter()
    fn_counter: Counter[str] = Counter()

    for r in rows:
        fn = (r.get("filename") or "").strip() or "(no filename)"
        fn_counter[fn] += 1
        if r.get("needs_review"):
            needs += 1
            raw = (r.get("review_reason_codes") or "").strip()
            if not raw:
                no_code += 1
            else:
                for part in raw.split(";"):
                    c = part.strip()
                    if c in ALLOWED_REASON_CODES:
                        code_counts[c] += 1
        else:
            appr += 1

    print(f"=== Submission failure analysis (last {len(rows)} rows) ===\n")
    print(f"Needs review: {needs}")
    print(f"Approved:     {appr}")
    print(f"Needs review but NO reason codes (legacy / gap): {no_code}\n")

    print("--- Per reason code (row can have multiple codes) ---")
    for code, cnt in code_counts.most_common():
        print(f"  {cnt:5d}  {code}")

    print("\n--- Top duplicate filenames (same file → multiple DB rows) ---")
    dupes = [(fn, n) for fn, n in fn_counter.most_common(25) if n > 1]
    if not dupes:
        print("  (none in this window)")
    else:
        for fn, n in dupes:
            short = fn if len(fn) <= 70 else fn[:67] + "..."
            print(f"  {n:3d}×  {short}")

    print("\n--- Improving during contest (quick read) ---")
    print("  • High MISSING_* → OCR/extraction or empty form; check scans + extract_ifi.")
    print("  • High EMPTY_ESSAY / SHORT_ESSAY → segmentation or real short essays.")
    print("  • High TEMPLATE_ONLY → users uploading blank forms.")
    print("  • Many duplicate filenames → chunking/re-uploads; consider dedupe rules for reporting.")


if __name__ == "__main__":
    main()
