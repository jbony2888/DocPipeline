#!/usr/bin/env python3
"""
Ingest previously exported web/worker log files into normalized JSONL.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.export_logs import ingest_logs_from_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse exported IFI logs into JSONL rows.")
    parser.add_argument("--log-dir", required=True, help="Directory containing .log/.txt files.")
    parser.add_argument("--out-jsonl", required=True, help="Output JSONL path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log_dir = Path(args.log_dir).resolve()
    out_path = Path(args.out_jsonl).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = ingest_logs_from_files(log_dir, out_path)
    print(f"Ingested {count} log rows into {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
