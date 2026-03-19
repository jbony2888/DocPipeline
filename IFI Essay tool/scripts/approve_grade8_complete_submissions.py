#!/usr/bin/env python3
"""
Mark submissions as approved when they have all required data and no review reason codes.
Updates both admin dashboard and user review views.

Usage:
  python scripts/approve_grade8_complete_submissions.py           # dry run (Grade 8 only)
  python scripts/approve_grade8_complete_submissions.py --execute # apply updates
  python scripts/approve_grade8_complete_submissions.py --all-grades --execute  # all grades
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
    parser = argparse.ArgumentParser(description="Approve submissions with complete data and no reason codes")
    parser.add_argument("--execute", action="store_true", help="Apply updates. Default is dry run.")
    parser.add_argument("--all-grades", action="store_true", help="Include all grades (default: Grade 8 only)")
    parser.add_argument("--grade", type=str, help="Specific grade only (e.g. 10)")
    parser.add_argument("--verbose", action="store_true", help="Show all needs_review rows before filtering")
    args = parser.parse_args()

    from pipeline.supabase_db import _get_service_role_client

    client = _get_service_role_client()
    if not client:
        print("❌ Could not connect to Supabase (missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY)")
        return 1

    # Fetch Grade 8 submissions with needs_review=True (grade may be stored as 8 or "8")
    result = (
        client.table("submissions")
        .select("submission_id, student_name, school_name, grade, needs_review, review_reason_codes, owner_user_id, filename")
        .eq("needs_review", True)
        .execute()
    )
    rows = result.data or []
    grade_filter = None
    if args.all_grades:
        grade_filter = "all grades"
    elif args.grade:
        grade_filter = f"Grade {args.grade}"
        rows = [r for r in rows if str(r.get("grade") or "").strip() == str(args.grade).strip()]
    else:
        grade_filter = "Grade 8"
        rows = [r for r in rows if str(r.get("grade") or "").strip() == "8"]

    if args.verbose:
        print(f"needs_review=True rows ({grade_filter}): {len(rows)}")
        for r in rows[:15]:
            print(f"  {r.get('submission_id')} | grade={r.get('grade')} | reason={repr((r.get('review_reason_codes') or '')[:40])} | student={bool(r.get('student_name'))} school={bool(r.get('school_name'))}")
        if len(rows) > 15:
            print(f"  ... and {len(rows) - 15} more")

    # Filter: all data present and no substantive reason codes
    # Approve when reason is empty or "PENDING_REVIEW" (generic placeholder, no specific issue)
    to_approve = []
    for r in rows:
        student = (r.get("student_name") or "").strip()
        school = (r.get("school_name") or "").strip()
        grade = r.get("grade")
        reason = (r.get("review_reason_codes") or "").strip()
        reason_ok = not reason or reason == "PENDING_REVIEW"
        if student and school and grade is not None and reason_ok:
            to_approve.append(r)

    scope = grade_filter
    if not to_approve:
        print(f"✅ No {scope} submissions need approval (all complete ones are already approved or none match criteria)")
        return 0

    print(f"Found {len(to_approve)} {scope} submission(s) to approve (all data present, no reason codes):")
    for r in to_approve:
        print(f"  {r.get('submission_id')} | {r.get('student_name')} | {r.get('school_name')} | {r.get('filename', '')[:40]}")
    print("-" * 80)

    if not args.execute:
        print("Dry run. Run with --execute to apply updates.")
        return 0

    updated = 0
    for r in to_approve:
        sid = r["submission_id"]
        try:
            client.table("submissions").update({
                "needs_review": False,
                "review_reason_codes": "",
            }).eq("submission_id", sid).execute()
            updated += 1
            print(f"  ✓ {sid}")
        except Exception as e:
            print(f"  ✗ {sid}: {e}")

    print(f"\n✅ Updated {updated} submission(s) to approved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
