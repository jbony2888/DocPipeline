#!/usr/bin/env python3
"""
Delete submission records (and their storage) created before a cutoff date.
Use for removing test data. Requires service role key.

Usage:
  python scripts/cleanup_test_records_before_date.py                    # dry run (default: before 2026-03-01)
  python scripts/cleanup_test_records_before_date.py --archive-to archived_test_records --execute  # download first, then delete
  python scripts/cleanup_test_records_before_date.py --execute          # delete only (no archive)
  python scripts/cleanup_test_records_before_date.py --date 2026-02-15  # custom cutoff (dry run)
  python scripts/cleanup_test_records_before_date.py --date 2026-03-01 --execute
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


def _safe_filename(name: str, max_len: int = 80) -> str:
    """Sanitize filename for filesystem."""
    s = re.sub(r'[^\w\s\-\.]', '_', str(name or ""))
    s = re.sub(r'\s+', '_', s).strip("_")
    return (s[:max_len] if s else "unknown").rstrip(".")


def main():
    parser = argparse.ArgumentParser(description="Delete test submissions before cutoff date")
    parser.add_argument("--date", default="2026-03-01", help="Cutoff date (YYYY-MM-DD). Records created before this are deleted.")
    parser.add_argument("--execute", action="store_true", help="Actually delete. Default is dry run.")
    parser.add_argument("--confirm", action="store_true", help="Show full record details to confirm test vs real before deleting.")
    parser.add_argument("--archive-to", metavar="FOLDER", help="Download PDFs to this folder before deleting. Creates folder if missing.")
    args = parser.parse_args()

    from pipeline.supabase_db import _get_service_role_client, delete_record as delete_db_record
    from pipeline.supabase_storage import delete_artifact_dir, download_original_with_service_role, BUCKET_NAME

    client = _get_service_role_client()
    if not client:
        print("❌ Could not connect to Supabase (missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY)")
        return 1

    cutoff = args.date.strip()
    if len(cutoff) == 10:
        cutoff += "T00:00:00"
    elif "T" not in cutoff:
        cutoff += "T00:00:00"

    # Fetch records created before cutoff
    select_fields = "submission_id, owner_user_id, filename, created_at, artifact_dir"
    if args.confirm:
        select_fields += ", student_name, school_name, grade, teacher_name"
    result = (
        client.table("submissions")
        .select(select_fields)
        .lt("created_at", cutoff)
        .order("created_at", desc=False)
        .execute()
    )
    records = result.data or []

    if not records:
        print(f"✅ No records found with created_at before {args.date}")
        return 0

    print(f"Found {len(records)} record(s) with created_at before {args.date}")
    print("-" * 80)
    if args.confirm:
        for r in records:
            student = (r.get("student_name") or "(none)")[:28]
            school = (r.get("school_name") or "(none)")[:22]
            fname = r.get("filename", "?")
            owner_short = (r.get("owner_user_id") or "?")[:8] + "..." if r.get("owner_user_id") else "?"
            created = (r.get("created_at") or "")[:19]
            print(f"  {r.get('submission_id')} | {fname[:38]:<38} | {created}")
            print(f"      student={student:<28} school={school:<22} owner={owner_short}")
        print("-" * 80)
        print("\nReview above. If these look like test records, run with --execute to delete.")
    else:
        for r in records[:20]:
            print(f"  {r.get('submission_id')} | {r.get('filename', '?')[:40]} | {r.get('created_at', '')[:19]}")
        if len(records) > 20:
            print(f"  ... and {len(records) - 20} more")
        print("-" * 80)

    # Archive first if requested
    archive_dir = None
    if args.archive_to:
        archive_dir = PROJECT_ROOT / args.archive_to.strip()
        archive_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n📥 Archiving to {archive_dir}...")
        manifest = []
        for r in records:
            sid = r.get("submission_id")
            artifact_dir = r.get("artifact_dir", "").strip()
            fname = r.get("filename", "unknown.pdf")
            if not artifact_dir:
                print(f"  ⚠ {sid}: no artifact_dir, skipping download")
                m = {k: str(v) if v is not None else None for k, v in r.items()}
                manifest.append({**m, "archived": False, "reason": "no artifact_dir"})
                continue
            file_bytes, _ = download_original_with_service_role(client, artifact_dir, fname)
            if not file_bytes:
                print(f"  ⚠ {sid}: file not found in storage")
                m = {k: str(v) if v is not None else None for k, v in r.items()}
                manifest.append({**m, "archived": False, "reason": "not found in storage"})
                continue
            base = _safe_filename(Path(fname).stem)
            ext = Path(fname).suffix or ".pdf"
            local_name = f"{sid}_{base}{ext}"
            out_path = archive_dir / local_name
            out_path.write_bytes(file_bytes)
            print(f"  ✓ {local_name}")
            m = {k: str(v) if v is not None else None for k, v in r.items() if k != "artifact_dir"}
            m["archived_file"] = local_name
            manifest.append(m)
        (archive_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (archive_dir / "README.md").write_text(
            f"# Archived test records (before {args.date})\n\n"
            f"Downloaded {len(manifest)} records before deletion from Supabase.\n"
            f"See manifest.json for record metadata.\n",
            encoding="utf-8"
        )
        print(f"  Saved manifest.json and README.md ({len(manifest)} records)")
        print("-" * 80)

    if not args.execute:
        print("\n🔍 DRY RUN. No records deleted.")
        if archive_dir:
            print(f"   Archived {len(records)} files to {archive_dir}")
        print("   Run with --execute to delete these records and their storage.")
        return 0

    print("\n🗑️  Deleting...")
    deleted = 0
    errors = []
    for r in records:
        sid = r.get("submission_id")
        owner = r.get("owner_user_id")
        artifact_dir = r.get("artifact_dir", "").strip()
        try:
            if artifact_dir:
                ok = delete_artifact_dir(artifact_dir, client)
                if not ok:
                    errors.append(f"{sid}: storage cleanup failed")
                    continue
            if delete_db_record(sid, owner_user_id=owner, access_token=None, refresh_token=None):
                deleted += 1
                print(f"  ✓ {sid} ({r.get('filename', '')[:30]})")
            else:
                errors.append(f"{sid}: db delete failed")
        except Exception as e:
            errors.append(f"{sid}: {e}")

    print(f"\n✅ Deleted {deleted}/{len(records)} records.")
    if errors:
        print("Errors:", errors)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
