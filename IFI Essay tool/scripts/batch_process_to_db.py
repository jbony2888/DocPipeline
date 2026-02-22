#!/usr/bin/env python3
"""
Run end-to-end processing for a batch of essay files and log each result.

This script:
1) Reads each PDF/image from an input directory
2) Runs jobs.process_submission.process_submission_job
3) Verifies the record exists in Supabase submissions table
4) Writes one JSON line per file to an output log
5) Writes a summary JSON file
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

from jobs.process_submission import process_submission_job


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
    parser.add_argument("--input-dir", default="docs", help="Directory containing files to process.")
    parser.add_argument("--pattern", default="*.pdf", help="Glob pattern to match files.")
    parser.add_argument("--owner-user-id", default=None, help="Owner user UUID for saved records.")
    parser.add_argument("--access-token", default="terminal-batch-test", help="Access token passed to job call.")
    parser.add_argument("--ocr-provider", default="google", help="OCR provider name.")
    parser.add_argument("--out", default=None, help="Output JSONL path.")
    parser.add_argument("--max-files", type=int, default=None, help="Optional limit for file count.")
    args = parser.parse_args()

    project_root = PROJECT_ROOT
    load_dotenv(project_root / ".env")

    owner_user_id = find_owner_user_id(args.owner_user_id, project_root)
    if not owner_user_id:
        print("ERROR: owner_user_id not found. Pass --owner-user-id or set OWNER_USER_ID in env.")
        return 2

    input_dir = (project_root / args.input_dir).resolve()
    if not input_dir.exists():
        print(f"ERROR: input directory does not exist: {input_dir}")
        return 2

    files = sorted([p for p in input_dir.glob(args.pattern) if p.is_file()])
    if args.max_files:
        files = files[: args.max_files]

    if not files:
        print(f"ERROR: no files matched {args.pattern} in {input_dir}")
        return 2

    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(args.out) if args.out else logs_dir / f"batch_process_{timestamp}.jsonl"
    if not out_path.is_absolute():
        out_path = (project_root / out_path).resolve()

    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "owner_user_id": owner_user_id,
        "input_dir": str(input_dir),
        "pattern": args.pattern,
        "ocr_provider": args.ocr_provider,
        "total_files": len(files),
        "success_count": 0,
        "failed_count": 0,
        "failed_files": [],
        "verified_count": 0,
    }

    print(f"Processing {len(files)} file(s) from {input_dir}")
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
