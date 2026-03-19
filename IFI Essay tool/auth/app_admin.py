"""
App-level admin: users whose email is listed in ADMIN_EMAILS get access to
/admin (all submissions) when logged in via Supabase — no separate admin token.

Set ADMIN_EMAILS in the environment as a comma-separated list, e.g.:
  ADMIN_EMAILS=jerrybony5@gmail.com,other@example.com
"""

import os
from typing import Optional, Set

# Always treated as app admins (in addition to ADMIN_EMAILS). Keep small and intentional.
_BUILTIN_APP_ADMIN_EMAILS: frozenset[str] = frozenset(
    {
        "jerrybony5@gmail.com",
    }
)


def get_app_admin_emails() -> Set[str]:
    """Lowercase emails that may use the admin dashboard while logged in."""
    emails: Set[str] = set(_BUILTIN_APP_ADMIN_EMAILS)
    raw = (os.environ.get("ADMIN_EMAILS") or "").strip()
    for part in raw.split(","):
        e = part.strip().lower()
        if e and "@" in e:
            emails.add(e)
    return emails


def is_app_admin_email(email: Optional[str]) -> bool:
    if not email:
        return False
    return str(email).strip().lower() in get_app_admin_emails()
