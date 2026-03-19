#!/usr/bin/env python3
"""
Query Supabase for submission counts. Run from project root.
Usage: python scripts/count_submissions.py
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


def main():
    from pipeline.supabase_db import _get_service_role_client

    client = _get_service_role_client()
    if not client:
        print("❌ Could not connect to Supabase (missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY)")
        return 1

    # Total count
    r = client.table("submissions").select("submission_id", count="exact", head=True).execute()
    total = r.count if hasattr(r, "count") and r.count is not None else len(r.data or [])

    # Needs review
    r2 = client.table("submissions").select("submission_id", count="exact", head=True).eq("needs_review", True).execute()
    needs_review = r2.count if hasattr(r2, "count") and r2.count is not None else len(r2.data or [])

    # By owner (top uploaders)
    r3 = client.table("submissions").select("owner_user_id").execute()
    from collections import Counter
    by_owner = Counter(rec.get("owner_user_id") for rec in (r3.data or []) if rec.get("owner_user_id"))

    print("Supabase submissions")
    print("-" * 40)
    print(f"  Total:          {total}")
    print(f"  Needs review:   {needs_review}")
    print(f"  Clean:          {total - needs_review}")
    print("-" * 40)
    print("  Top uploaders (by owner_user_id):")
    for uid, count in by_owner.most_common(10):
        short = (uid or "?")[:8] + "..." if (uid and len(uid) > 8) else (uid or "?")
        print(f"    {short}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
