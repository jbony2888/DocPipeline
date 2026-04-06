#!/usr/bin/env python3
"""
Run end-to-end processing for a batch of essay files and log each result.

This script:
1) Reads each PDF/image from one or more input directories (repeat --input-dir)
2) Deduplicates by basename (first directory wins)
3) Optionally skips files already in DB (--only-missing / --skip-if-filename-in-db)
4) Runs jobs.process_submission.process_submission_job
5) Verifies the record exists in Supabase submissions table
6) Writes one JSON line per file to an output log and a summary JSON file

Restore only missing fatherhood essays from disk:
  python scripts/restore_missing_essays_from_disk.py --dry-run
  python scripts/restore_missing_essays_from_disk.py --owner-user-id <uuid>
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from supabase import create_client

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jobs.process_submission import process_submission_job
from pipeline.essay_precheck import is_likely_contest_essay_pdf


def find_owner_user_id(explicit_owner: Optional[str], project_root: Path) -> Optional[str]:
    if explicit_owner:
        return explicit_owner

    for env_key in ("OWNER_USER_ID", "TEST_OWNER_USER_ID"):
        value = os.environ.get(env_key)
        if value:
            return value

    log_path = project_root / "logs" / "processing.log"
    if log_path.exists():
        text = log_path.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"owner_user_id='([0-9a-fA-F-]{36})'", text)
        if match:
            return match.group(1)

    return None


def _fetch_existing_filenames() -> set[str]:
    """Distinct non-empty submission filenames (for skip-existing)."""
    from pipeline.supabase_db import _get_service_role_client

    sb = _get_service_role_client()
    if not sb:
        return set()
    names: set[str] = set()
    page_size = 1000
    offset = 0
    while True:
        chunk = (
            sb.table("submissions")
            .select("filename")
            .range(offset, offset + page_size - 1)
            .execute()
            .data
            or []
        )
        for row in chunk:
            fn = str(row.get("filename") or "").strip()
            if fn:
                names.add(fn)
        if len(chunk) < page_size:
            break
        offset += page_size
    return names


def verify_saved(submission_id: str, owner_user_id: str) -> Dict[str, Any]:
    supabase_url = os.environ.get("SUPABASE_URL")
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_role_key:
        return {"verified": False, "error": "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY"}

    try:
        admin = create_client(supabase_url.rstrip("/"), service_role_key)
        result = (
            admin.table("submissions")
            .select("submission_id, owner_user_id, filename, needs_review, review_reason_codes, word_count")
            .eq("submission_id", submission_id)
            .eq("owner_user_id", owner_user_id)
            .limit(1)
            .execute()
        )
        row = result.data[0] if result.data else None
        return {"verified": row is not None, "row": row}
    except Exception as exc:
        return {"verified": False, "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch-process essays and log each DB result.")
    parser.add_argument(
        "--input-dir",
        action="append",
        default=[],
        metavar="DIR",
        help="Directory containing files (repeatable; earlier dirs win on duplicate basenames). Default: docs",
    )
    parser.add_argument("--pattern", default="*.pdf", help="Glob pattern to match files.")
    parser.add_argument("--owner-user-id", default=None, help="Owner user UUID for saved records.")
    parser.add_argument("--access-token", default="terminal-batch-test", help="Access token passed to job call.")
    parser.add_argument("--ocr-provider", default="google", help="OCR provider name.")
    parser.add_argument("--out", default=None, help="Output JSONL path.")
    parser.add_argument("--max-files", type=int, default=None, help="Optional limit for file count.")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N files (for batch processing).")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N files (after offset).")
    parser.add_argument(
        "--skip-if-filename-in-db",
        action="store_true",
        help="Skip files whose basename already exists as submissions.filename (any row).",
    )
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Alias for --skip-if-filename-in-db (process only files not already in the database).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be processed, then exit (no full pipeline / no DB writes). "
        "With --require-contest-essay-filter, may OCR page-1 top strip on scanned PDFs.",
    )
    parser.add_argument(
        "--require-contest-essay-filter",
        action="store_true",
        help="Skip PDFs that fail contest-essay precheck (not IFI forms / not essay-like).",
    )
    args = parser.parse_args()

    project_root = PROJECT_ROOT
    load_dotenv(project_root / ".env")

    owner_user_id = find_owner_user_id(args.owner_user_id, project_root)
    if not args.dry_run and not owner_user_id:
        print("ERROR: owner_user_id not found. Pass --owner-user-id or set OWNER_USER_ID in env.")
        return 2

    dir_args = args.input_dir if args.input_dir else ["docs"]
    input_dirs: list[Path] = []
    for raw in dir_args:
        raw_in = Path(raw).expanduser()
        d = raw_in.resolve() if raw_in.is_absolute() else (project_root / raw_in).resolve()
        if not d.is_dir():
            print(f"WARN: skipping missing directory: {d}")
            continue
        input_dirs.append(d)
    if not input_dirs:
        print("ERROR: no valid input directories")
        return 2

    # One path per basename: first directory in list wins (e.g. Downloads copy before repo copy).
    seen_basenames: set[str] = set()
    files: list[Path] = []
    for d in input_dirs:
        for p in sorted(d.glob(args.pattern)):
            if p.is_file() and p.name not in seen_basenames:
                seen_basenames.add(p.name)
                files.append(p)
    files.sort(key=lambda p: p.name.casefold())

    if args.offset:
        files = files[args.offset:]
    cap = args.limit if args.limit is not None else args.max_files
    if cap is not None:
        files = files[:cap]

    skipped_existing = 0
    skip_db = args.skip_if_filename_in_db or args.only_missing
    if skip_db:
        existing = _fetch_existing_filenames()
        before = len(files)
        files = [p for p in files if p.name not in existing]
        skipped_existing = before - len(files)
        if skipped_existing:
            print(f"Skipping {skipped_existing} file(s) already in DB (by filename).")

    if not files:
        print(f"ERROR: no files to process after scanning {len(input_dirs)} dir(s) and filters")
        return 2

    skipped_precheck: list[dict[str, Any]] = []
    if args.require_contest_essay_filter:
        kept: list[Path] = []
        for p in files:
            ok, reason = is_likely_contest_essay_pdf(str(p), ocr_provider_name=args.ocr_provider)
            if ok:
                kept.append(p)
            else:
                skipped_precheck.append({"filename": p.name, "path": str(p), "reason": reason})
        if skipped_precheck:
            print(f"Contest-essay precheck: skipping {len(skipped_precheck)} non-essay / unrecognized file(s).")
            for row in skipped_precheck[:50]:
                print(f"  skip: {row['filename']} ({row['reason']})")
            if len(skipped_precheck) > 50:
                print(f"  ... and {len(skipped_precheck) - 50} more")
        files = kept
        if not files:
            print("ERROR: no files left after contest-essay precheck")
            return 2

    if args.dry_run:
        print("Dry run: would process these files (not running pipeline)")
        for i, p in enumerate(files, 1):
            print(f"  {i}. {p.name}")
            print(f"      {p}")
        print(f"Total: {len(files)}")
        if skipped_precheck:
            print(f"(Precheck skipped {len(skipped_precheck)} file(s); see lines above.)")
        return 0

    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(args.out) if args.out else logs_dir / f"batch_process_{timestamp}.jsonl"
    if not out_path.is_absolute():
        out_path = (project_root / out_path).resolve()

    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "owner_user_id": owner_user_id,
        "input_dirs": [str(d) for d in input_dirs],
        "pattern": args.pattern,
        "ocr_provider": args.ocr_provider,
        "total_files": len(files),
        "skipped_existing_in_db": skipped_existing,
        "skipped_contest_precheck": len(skipped_precheck),
        "skipped_contest_precheck_files": skipped_precheck,
        "only_missing": skip_db,
        "require_contest_essay_filter": bool(args.require_contest_essay_filter),
        "success_count": 0,
        "failed_count": 0,
        "failed_files": [],
        "verified_count": 0,
    }

    print(f"Processing {len(files)} file(s) from {len(input_dirs)} directory(ies):")
    for d in input_dirs:
        print(f"  {d}")
    print(f"owner_user_id={owner_user_id}")
    print(f"log_file={out_path}")

    with out_path.open("w", encoding="utf-8") as log_file:
        for index, file_path in enumerate(files, start=1):
            started = time.time()
            entry: Dict[str, Any] = {
                "index": index,
                "filename": file_path.name,
                "path": str(file_path),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "status": "unknown",
            }

            try:
                file_bytes = file_path.read_bytes()
                result = process_submission_job(
                    file_bytes=file_bytes,
                    filename=file_path.name,
                    owner_user_id=owner_user_id,
                    access_token=args.access_token,
                    ocr_provider=args.ocr_provider,
                    upload_batch_id=None,
                )
                entry["result"] = result
                entry["submission_id"] = result.get("submission_id")
                entry["status"] = result.get("status", "success")
                entry["duration_seconds"] = round(time.time() - started, 3)

                verify = verify_saved(entry["submission_id"], owner_user_id) if entry.get("submission_id") else {"verified": False, "error": "No submission_id"}
                entry["db_verify"] = verify

                if entry["status"] == "success":
                    summary["success_count"] += 1
                else:
                    summary["failed_count"] += 1
                    summary["failed_files"].append(file_path.name)
                if verify.get("verified"):
                    summary["verified_count"] += 1
            except Exception as exc:
                entry["status"] = "failed"
                entry["error"] = str(exc)
                entry["duration_seconds"] = round(time.time() - started, 3)
                summary["failed_count"] += 1
                summary["failed_files"].append(file_path.name)
                print(f"  ❌ FAILED: {file_path.name}: {exc}")

            log_file.write(json.dumps(entry, ensure_ascii=True) + "\n")
            log_file.flush()
            print(f"[{index}/{len(files)}] {file_path.name} -> {entry['status']}")

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    summary_path = out_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Write failed-files list for easy review
    failed_path = out_path.with_suffix(".failed.txt")
    if summary["failed_files"]:
        failed_path.write_text("\n".join(summary["failed_files"]) + "\n", encoding="utf-8")

    print("\nSummary")
    print(json.dumps(summary, indent=2))
    if summary["failed_files"]:
        print("\n--- Failed documents (for review) ---")
        for f in summary["failed_files"]:
            print(f"  {f}")
        print(f"Failed list also saved to: {failed_path}")
    print(f"\nPer-file log: {out_path}")
    print(f"Summary log: {summary_path}")

    return 0 if summary["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
