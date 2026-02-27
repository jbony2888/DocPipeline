#!/usr/bin/env python3
"""
Check that required environment variables are set.
Loads .env from project root. Use before starting the app or in CI.
Usage: python scripts/check_env.py
"""

import os
import sys
from pathlib import Path

# Project root (parent of scripts/)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

# Required for app + worker (Docker or local)
REQUIRED = [
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "REDIS_URL",
    "FLASK_SECRET_KEY",
]

# At least one of these required for OCR
OCR_KEYS = [
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_VISION_CREDENTIALS_JSON",
]

# Optional but recommended
OPTIONAL = [
    "GROQ_API_KEY",
    "GOOGLE_CREDENTIALS_PATH",
    "WORKER_ID",
    "APP_URL",
    "EMAIL",
    "GMAIL_PASSWORD",
]


def _load_dotenv():
    try:
        from dotenv import load_dotenv
        if ENV_PATH.exists():
            load_dotenv(ENV_PATH)
        else:
            load_dotenv()
    except ImportError:
        pass


def _is_set(key: str) -> bool:
    val = os.environ.get(key)
    return val is not None and str(val).strip() != ""


def main() -> int:
    _load_dotenv()

    missing = []
    for key in REQUIRED:
        if not _is_set(key):
            missing.append(key)

    # OCR: at least one of GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_CLOUD_VISION_CREDENTIALS_JSON
    has_ocr = any(_is_set(k) for k in OCR_KEYS)
    if not has_ocr:
        missing.append("(one of " + ", ".join(OCR_KEYS) + ")")

    # Report
    print("Environment check (from .env or shell)")
    print("-" * 50)
    for key in REQUIRED:
        status = "OK" if _is_set(key) else "MISSING"
        print(f"  {key}: {status}")
    print(f"  OCR credentials (one of {', '.join(OCR_KEYS)}): {'OK' if has_ocr else 'MISSING'}")
    for key in OPTIONAL:
        status = "set" if _is_set(key) else "not set"
        print(f"  {key} (optional): {status}")
    print("-" * 50)

    if missing:
        print("Missing required:", ", ".join(missing))
        print("Copy .env.example to .env and fill in values.")
        return 1
    print("All required keys are set.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
