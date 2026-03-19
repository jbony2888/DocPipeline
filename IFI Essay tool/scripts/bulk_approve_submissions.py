#!/usr/bin/env python3
"""
Bulk approve submissions to clear review signals from the dashboard.
Sets needs_review=False and review_reason_codes="" for all matching submissions.

Usage:
  python scripts/bulk_approve_submissions.py              # dry run
  python scripts/bulk_approve_submissions.py --execute    # apply updates
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
    parser = argparse.ArgumentParser(description="Bulk approve submissions to remove review signals")
    parser.add_argument("--execute", action="store_true", help="Apply updates. Default is dry run.")
    args = parser.parse_args()

    from pipeline.supabase_db import _get_service_role_client

    client = _get_service_role_client()
    if not client:
        print("❌ Could not connect to Supabase")
        return 1

    r = client.table("submissions").select("submission_id, filename, student_name, school_name, grade").eq("needs_review", True).execute()
    rows = r.data or []

    if not rows:
        print("✅ No submissions need approval (all are already approved)")
        return 0

    print(f"Found {len(rows)} submission(s) with needs_review=True")
    for r in rows[:10]:
        print(f"  {r.get('submission_id')} | {r.get('student_name') or '?'} | {r.get('school_name') or '?'} | {r.get('grade') or '?'} | {str(r.get('filename', ''))[:40]}")
    if len(rows) > 10:
        print(f"  ... and {len(rows) - 10} more")
    print("-" * 80)

    if not args.execute:
        print("Dry run. Run with --execute to approve all and remove review signals.")
        return 0

    updated = 0
    for r in rows:
        sid = r["submission_id"]
        try:
            client.table("submissions").update({
                "needs_review": False,
                "review_reason_codes": "",
            }).eq("submission_id", sid).execute()
            updated += 1
        except Exception as e:
            print(f"  ✗ {sid}: {e}")

    print(f"✅ Approved {updated} submission(s). Review signals cleared.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
