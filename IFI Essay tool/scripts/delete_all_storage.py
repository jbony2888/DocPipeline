#!/usr/bin/env python3
"""
Delete all files from the Supabase Storage 'essay-submissions' bucket.

Uses SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from .env.
Requires service role key for storage admin access.

Usage (run from anywhere - script loads .env from IFI Essay tool dir):
  python "IFI Essay tool/scripts/delete_all_storage.py"           # dry run
  python "IFI Essay tool/scripts/delete_all_storage.py" --delete  # delete all
"""

import io
import os
import sys
from contextlib import contextmanager
from pathlib import Path

# Resolve project root (IFI Essay tool directory)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

# Load .env before any supabase imports
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# Normalize Supabase URL (storage3 requires trailing slash)
_supabase_url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
if _supabase_url:
    _supabase_url = _supabase_url + "/"
    os.environ["SUPABASE_URL"] = _supabase_url


@contextmanager
def _silence_storage_print():
    """Suppress storage3's 'Storage endpoint URL should have a trailing slash' print."""
    _old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = _old


def list_all_paths(sb, bucket: str, prefix: str = "") -> list:
    """Recursively list all file paths under a prefix."""
    paths = []
    try:
        result = sb.storage.from_(bucket).list(prefix if prefix else None, {"limit": 1000})
    except Exception as e:
        print(f"  ⚠️ List error at '{prefix or 'root'}': {e}", file=sys.stderr)
        return paths

    for item in result or []:
        name = item.get("name") or item.get("id")
        if not name:
            continue
        full_path = f"{prefix}/{name}" if prefix else name

        # If this path has children, recurse; otherwise it's a file
        try:
            children = sb.storage.from_(bucket).list(full_path, {"limit": 1})
            if children:
                paths.extend(list_all_paths(sb, bucket, full_path))
                continue
        except Exception:
            pass
        paths.append(full_path)

    return paths


def main():
    do_delete = "--delete" in sys.argv

    supabase_url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    if supabase_url:
        supabase_url = supabase_url + "/"
    service_key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    bucket = "essay-submissions"

    if not supabase_url or not service_key:
        print("❌ Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env")
        sys.exit(1)

    from supabase import create_client

    # Create client and trigger storage init while silencing storage3's print
    with _silence_storage_print():
        sb = create_client(supabase_url, service_key)
        sb.storage.from_(bucket).list(None, {"limit": 1})  # trigger init

    print(f"📂 Listing all files in bucket '{bucket}'...")
    paths = list_all_paths(sb, bucket)
    print(f"   Found {len(paths)} file(s)")

    if not paths:
        print("   Nothing to delete.")
        return

    if not do_delete:
        print("\n   Paths (dry run, use --delete to actually delete):")
        for p in paths[:50]:
            print(f"     {p}")
        if len(paths) > 50:
            print(f"     ... and {len(paths) - 50} more")
        print("\n   Run with --delete to remove these files.")
        return

    batch_size = 100
    deleted = 0
    errors = []
    for i in range(0, len(paths), batch_size):
        batch = paths[i : i + batch_size]
        try:
            sb.storage.from_(bucket).remove(batch)
            deleted += len(batch)
            print(f"   Deleted batch {i // batch_size + 1}: {len(batch)} file(s)")
        except Exception as e:
            errors.append(str(e))
            print(f"   ⚠️ Batch error: {e}")

    if errors:
        print(f"\n❌ {len(errors)} batch(es) failed. Deleted {deleted}/{len(paths)} files.")
        sys.exit(1)
    print(f"\n✅ Deleted {deleted} file(s) from '{bucket}'.")


if __name__ == "__main__":
    main()
