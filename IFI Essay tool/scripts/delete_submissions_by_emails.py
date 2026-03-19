#!/usr/bin/env python3
"""
Delete submissions ONLY for these Supabase Auth emails (no other users touched):

  - scotmarcotte@4dads.org
  - scotmarcotte@comcast.net
  - Scot_Marcotte@ajg.com  (matched case-insensitively)

Flow: resolve user UUID(s) from Auth → load submissions where owner_user_id is ONLY those
UUIDs → delete Storage for those rows → delete those submission rows.

Default is DRY RUN. Pass --execute to apply.

Usage (from IFI Essay tool directory):
  python scripts/delete_submissions_by_emails.py
  python scripts/delete_submissions_by_emails.py --execute

Requires: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY in environment (.env).

Does NOT delete Auth users — only public.submissions + essay-submissions files for those owners.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from supabase import create_client

from auth.supabase_client import normalize_supabase_url
from pipeline.supabase_storage import delete_artifact_dir

# Emails to match (case-insensitive)
TARGET_EMAILS = frozenset(
    {
        "scotmarcotte@4dads.org",
        "scotmarcotte@comcast.net",
        "scot_marcotte@ajg.com",
    }
)


def _service_client():
    url = normalize_supabase_url(os.environ.get("SUPABASE_URL"))
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        sys.exit(1)
    return create_client(url, key)


def _list_all_auth_users(sb):
    """Paginate GoTrue admin list_users."""
    page = 1
    per_page = 1000
    out = []
    while True:
        batch = sb.auth.admin.list_users(page=page, per_page=per_page)
        if not batch:
            break
        out.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return out


def _normalize_email(u) -> str:
    # supabase_auth User may use .email
    e = getattr(u, "email", None) or ""
    return str(e).strip().lower()


def _user_id(u) -> str:
    return str(getattr(u, "id", "") or "")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples (from repo folder 'IFI Essay tool'):\n"
            "  python scripts/delete_submissions_by_emails.py\n"
            "  python scripts/delete_submissions_by_emails.py --execute\n"
            "\n"
            "If you see: error: unrecognized arguments: # ...\n"
            "  Your shell passed extra words to Python (often a copy-pasted 'inline comment' "
            "or a fancy Unicode #). Run only the two lines above—nothing after the script name "
            "except optional --execute."
        ),
    )
    ap.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete storage + DB rows (default: dry run only)",
    )
    args = ap.parse_args()

    sb = _service_client()

    print("Resolving Auth users by email (case-insensitive)...")
    users = _list_all_auth_users(sb)
    matched = []
    for u in users:
        em = _normalize_email(u)
        if em in TARGET_EMAILS:
            matched.append((_user_id(u), em))

    if not matched:
        print("No Auth users found for:", ", ".join(sorted(TARGET_EMAILS)))
        print("(They may never have logged in, or email differs.)")
        sys.exit(0)

    seen_uid = set()
    unique_pairs = []
    for uid, em in matched:
        if uid and uid not in seen_uid:
            seen_uid.add(uid)
            unique_pairs.append((uid, em))

    print("Matched user(s):")
    for uid, em in unique_pairs:
        print(f"  {em}  ->  {uid}")

    all_rows: list[dict] = []
    for uid, _em in unique_pairs:
        res = (
            sb.table("submissions")
            .select("submission_id, artifact_dir, filename, owner_user_id, created_at")
            .eq("owner_user_id", uid)
            .execute()
        )
        rows = res.data or []
        all_rows.extend(rows)

    allowed_uids = frozenset(uid for uid, _ in unique_pairs)

    for r in all_rows:
        ou = str(r.get("owner_user_id") or "")
        if ou not in allowed_uids:
            print(f"ERROR: submission {r.get('submission_id')} owner {ou} not in allowlist — abort.", file=sys.stderr)
            sys.exit(1)

    print(f"\nSubmissions rows to delete (ONLY these {len(allowed_uids)} user id(s), no one else): {len(all_rows)}")
    for r in all_rows[:50]:
        print(
            f"  {r.get('submission_id')}  |  {r.get('filename') or ''}  |  {r.get('created_at') or ''}"
        )
    if len(all_rows) > 50:
        print(f"  ... and {len(all_rows) - 50} more")

    if not args.execute:
        print("\n*** DRY RUN — no changes. Re-run with --execute to delete ONLY the above. ***")
        return

    print("\n*** EXECUTING DELETE (submissions for listed emails only) ***")
    errors = []
    for r in all_rows:
        sid = r.get("submission_id")
        ou = str(r.get("owner_user_id") or "")
        if ou not in allowed_uids:
            errors.append(f"{sid}: SKIP owner {ou} not in allowlist")
            continue
        ad = (r.get("artifact_dir") or "").strip()
        if ad:
            try:
                if not delete_artifact_dir(ad, sb):
                    errors.append(f"{sid}: storage delete returned False")
            except Exception as e:
                errors.append(f"{sid}: storage {e}")
        try:
            sb.table("submissions").delete().eq("submission_id", sid).eq("owner_user_id", ou).execute()
        except Exception as e:
            errors.append(f"{sid}: db {e}")

    print(f"Storage cleanup attempts (rows with artifact_dir): {sum(1 for r in all_rows if (r.get('artifact_dir') or '').strip())}")
    print(f"DB deletes attempted: {len(all_rows)}")
    if errors:
        print("Warnings/errors:")
        for e in errors[:30]:
            print(f"  {e}")
        if len(errors) > 30:
            print(f"  ... {len(errors) - 30} more")
    print("Done.")


if __name__ == "__main__":
    main()
