#!/usr/bin/env python3
"""
Check that GROQ_API_KEY and Google Cloud Vision credentials are set in .env.
Reports missing keys only; never writes to .env or adds placeholders.
Usage: python scripts/ensure_api_keys.py
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

GROQ_KEY = "GROQ_API_KEY"
GOOGLE_APP_CREDS = "GOOGLE_APPLICATION_CREDENTIALS"
GOOGLE_CREDS_PATH = "GOOGLE_CREDENTIALS_PATH"
GOOGLE_JSON = "GOOGLE_CLOUD_VISION_CREDENTIALS_JSON"
GOOGLE_KEYS = [GOOGLE_APP_CREDS, GOOGLE_JSON]


def _parse_env(path: Path) -> dict:
    """Return dict of KEY -> True if key exists and has non-empty value."""
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$", line)
        if m:
            key, rest = m.group(1), m.group(2)
            val = rest.split("#")[0].strip().strip('"').strip("'")
            out[key] = bool(val)
    return out


def main() -> int:
    env = _parse_env(ENV_PATH)
    missing = []

    if not env.get(GROQ_KEY):
        missing.append(GROQ_KEY)
    if not any(env.get(k) for k in GOOGLE_KEYS):
        missing.append("(one of GOOGLE_APPLICATION_CREDENTIALS, GOOGLE_CLOUD_VISION_CREDENTIALS_JSON)")
    if env.get(GOOGLE_APP_CREDS) and not env.get(GOOGLE_CREDS_PATH):
        missing.append(GOOGLE_CREDS_PATH)

    if not missing:
        print("GROQ and Google Cloud Vision are set in .env")
        return 0

    print("Missing in .env (set real values only, no placeholders):", ", ".join(missing))
    return 1


if __name__ == "__main__":
    sys.exit(main())
