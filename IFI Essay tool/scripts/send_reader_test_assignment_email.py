#!/usr/bin/env python3
"""
Send the same "IFI essay reading batch" reader email as production (SMTP + portal link).

Loads IFI Essay tool/.env (run from repo: `cd "IFI Essay tool"`).

Portal link verification on docpipeline requires the SAME signing secret as the Render web service:
  export READER_PORTAL_SIGNING_SECRET='<copy FLASK_SECRET_KEY from Render dashboard>'
  export APP_URL='https://docpipeline.onrender.com'

If you omit READER_PORTAL_SIGNING_SECRET, this script uses FLASK_SECRET_KEY from .env (fine for
local testing with APP_URL=http://localhost:5000, not for prod unless secrets match).

Examples:
  cd "IFI Essay tool"
  python scripts/send_reader_test_assignment_email.py --to jerrybony5@gmail.com

  READER_PORTAL_SIGNING_SECRET='...from Render...' APP_URL='https://docpipeline.onrender.com' \\
    python scripts/send_reader_test_assignment_email.py --to jerrybony5@gmail.com
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer
from supabase import create_client

# project root = parent of scripts/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from admin.assignments_service import (  # noqa: E402
    add_batch_assignment,
    calculate_assignment_batch_count,
    count_approved_essays_for_batch,
    is_grade_level_assignment_school,
    list_assignment_submission_rows,
    STANDARD_SCHOOL_OPTIONS,
    upsert_reader_name,
)
from utils.email_notification import send_assignment_batch_email  # noqa: E402

_READER_PORTAL_TOKEN_SALT = "reader-portal-access"


def _signing_secret() -> str:
    return (
        (os.environ.get("READER_PORTAL_SIGNING_SECRET") or "").strip()
        or (os.environ.get("FLASK_SECRET_KEY") or "").strip()
        or (os.environ.get("SECRET_KEY") or "").strip()
        or "reader-portal-secret"
    )


def _portal_url(*, token: str, app_url: str) -> str:
    base = (app_url or "").strip().rstrip("/")
    if not base:
        raise SystemExit("APP_URL is empty. Set APP_URL (e.g. https://docpipeline.onrender.com).")
    return f"{base}/admin/reader-access?token={token}"


def _pick_school_grade(sb):
    for school in STANDARD_SCHOOL_OPTIONS:
        for grade in ["12", "11", "10", "9", "8", "7", "6", "5", "4", "3", "2", "1", "K"]:
            n = count_approved_essays_for_batch(sb, school=school, grade=str(grade))
            if n <= 0:
                continue
            tb = calculate_assignment_batch_count(n)
            if tb >= 1:
                return school, str(grade), n, tb
    raise SystemExit("No approved essays found for any standard school+grade bucket.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--to", default="jerrybony5@gmail.com", help="Reader email (recipient)")
    parser.add_argument("--name", default="Jerry Bony", help="Reader display name")
    parser.add_argument(
        "--app-url",
        default=(os.environ.get("APP_URL") or "").strip(),
        help="Base URL for portal link (default: APP_URL from env)",
    )
    args = parser.parse_args()

    to_email = str(args.to or "").strip().lower()
    if not to_email:
        print("--to is required", file=sys.stderr)
        return 2

    app_url = (args.app_url or "").strip()
    if not app_url:
        print(
            "Set APP_URL or pass --app-url (e.g. https://docpipeline.onrender.com for production links).",
            file=sys.stderr,
        )
        return 2

    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env", file=sys.stderr)
        return 2

    sb = create_client(url, key)
    reader = upsert_reader_name(sb, email=to_email, name=str(args.name or "").strip())
    if not reader or not reader.get("id"):
        print("Failed to upsert reader", file=sys.stderr)
        return 1
    reader_id = reader["id"]

    school, grade, pool_n, total_batches = _pick_school_grade(sb)
    add_batch_assignment(
        sb,
        reader_id=reader_id,
        school=school,
        grade=grade,
        batch_number=1,
        total_batches=total_batches,
    )

    rows = list_assignment_submission_rows(sb, school=school, grade=grade, batch_number=1)
    essay_count = len(rows)

    secret = _signing_secret()
    ser = URLSafeTimedSerializer(secret_key=secret, salt=_READER_PORTAL_TOKEN_SALT)
    token = ser.dumps({"email": to_email})
    portal_url = _portal_url(token=token, app_url=app_url)

    print("Sending assignment email…")
    print(f"  to={to_email}")
    print(f"  assignment: school={school!r} grade={grade!r} batch=1/{total_batches} essays_in_batch={essay_count} pool_approved={pool_n}")
    print(f"  portal base: {app_url}")
    if not os.environ.get("READER_PORTAL_SIGNING_SECRET") and "onrender.com" in app_url:
        print(
            "  NOTE: For this link to work on Render, READER_PORTAL_SIGNING_SECRET must match "
            "Render's FLASK_SECRET_KEY (see script docstring).",
            file=sys.stderr,
        )

    ok = send_assignment_batch_email(
        to_email=to_email,
        school=school,
        grade=grade,
        batch_number=1,
        total_batches=total_batches,
        essay_count=essay_count,
        portal_url=portal_url,
        grade_level_scope=is_grade_level_assignment_school(school),
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
