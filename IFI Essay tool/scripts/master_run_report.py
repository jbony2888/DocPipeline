#!/usr/bin/env python3
"""
Build one master report across all artifact runs.

Focus:
- failure analysis
- tools used (OCR/parse extraction methods + models)
- OCR quality versus parse outcomes
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def ocr_bucket(conf: Optional[float]) -> str:
    if conf is None:
        return "unknown"
    if conf < 0.5:
        return "low(<0.5)"
    if conf < 0.75:
        return "medium(0.5-0.75)"
    return "high(>=0.75)"


def load_run_records(artifacts_dir: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for subdir in sorted(artifacts_dir.iterdir()):
        if not subdir.is_dir():
            continue
        if subdir.name in {"log_exports", "master_reports"}:
            continue
        extraction_debug = read_json(subdir / "extraction_debug.json")
        validation = read_json(subdir / "validation.json")
        ocr = read_json(subdir / "ocr.json")
        structured = read_json(subdir / "structured.json")
        metadata = read_json(subdir / "metadata.json")
        if not any([extraction_debug, validation, ocr, structured, metadata]):
            continue

        required = (extraction_debug or {}).get("required_fields_found") or {}
        parse_success = bool(
            required.get("student_name")
            and required.get("school_name")
            and required.get("grade")
        )

        issues = (validation or {}).get("issues") or []
        if not isinstance(issues, list):
            issues = [str(issues)]
        reason_codes = (validation or {}).get("review_reason_codes") or ""
        reason_list = [r.strip().upper() for r in str(reason_codes).replace(",", ";").split(";") if r.strip()]

        confidence_avg = (ocr or {}).get("confidence_avg")
        if confidence_avg is None:
            confidence_avg = (structured or {}).get("ocr_confidence_avg")

        rec = {
            "submission_id": subdir.name,
            "created_at": (metadata or {}).get("created_at"),
            "ocr_confidence_avg": confidence_avg,
            "ocr_bucket": ocr_bucket(confidence_avg),
            "ocr_line_count": len((ocr or {}).get("lines") or []),
            "ocr_text_len": len((ocr or {}).get("text") or ""),
            "needs_review": bool((validation or {}).get("needs_review")),
            "issues": issues,
            "reason_codes": reason_list,
            "parse_success_required_fields": parse_success,
            "extraction_method": (extraction_debug or {}).get("extraction_method", "unknown"),
            "parse_model": (extraction_debug or {}).get("model", "unknown"),
            "ifi_doc_type": ((extraction_debug or {}).get("ifi_classification") or {}).get("doc_type"),
            "word_count": (structured or {}).get("word_count"),
        }
        records.append(rec)
    return records


def build_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(records)
    method_counts = Counter(r["extraction_method"] for r in records)
    model_counts = Counter(r["parse_model"] for r in records)
    issue_counts = Counter()
    reason_counts = Counter()
    by_bucket = Counter(r["ocr_bucket"] for r in records)
    parse_fail_by_bucket = Counter()
    parse_fail_by_method = Counter()
    parse_total_by_method = Counter()
    matrix = defaultdict(lambda: {"parse_success": 0, "parse_failure": 0})
    high_ocr_parse_fail: List[Dict[str, Any]] = []

    for r in records:
        for issue in r["issues"]:
            issue_counts[str(issue).upper()] += 1
        for reason in r["reason_codes"]:
            reason_counts[reason] += 1
        method = r["extraction_method"]
        bucket = r["ocr_bucket"]
        parse_total_by_method[method] += 1
        if r["parse_success_required_fields"]:
            matrix[bucket]["parse_success"] += 1
        else:
            matrix[bucket]["parse_failure"] += 1
            parse_fail_by_bucket[bucket] += 1
            parse_fail_by_method[method] += 1
            if (r["ocr_confidence_avg"] is not None) and r["ocr_confidence_avg"] >= 0.85:
                high_ocr_parse_fail.append(
                    {
                        "submission_id": r["submission_id"],
                        "ocr_confidence_avg": r["ocr_confidence_avg"],
                        "issues": r["issues"],
                        "reason_codes": r["reason_codes"],
                        "method": method,
                    }
                )

    fail_rate_by_method = {
        m: (parse_fail_by_method[m] / parse_total_by_method[m] if parse_total_by_method[m] else 0.0)
        for m in sorted(parse_total_by_method.keys())
    }
    fail_rate_by_bucket = {
        b: (parse_fail_by_bucket[b] / by_bucket[b] if by_bucket[b] else 0.0)
        for b in sorted(by_bucket.keys())
    }
    review_count = sum(1 for r in records if r["needs_review"])

    return {
        "total_runs_analyzed": total,
        "review_rate": (review_count / total) if total else 0.0,
        "tools_used": {
            "ocr_tools": {"unknown": total},  # Local artifacts do not persist OCR provider explicitly.
            "parse_extraction_methods": dict(method_counts),
            "parse_models": dict(model_counts),
        },
        "failure_patterns": {
            "issue_counts": dict(issue_counts),
            "reason_code_counts": dict(reason_counts),
            "parse_failure_rate_by_method": fail_rate_by_method,
            "parse_failure_rate_by_ocr_bucket": fail_rate_by_bucket,
            "ocr_vs_parse_matrix": dict(matrix),
            "high_ocr_parse_failure_candidates": high_ocr_parse_fail[:25],
        },
        "distributions": {
            "ocr_bucket_distribution": dict(by_bucket),
            "word_count_stats": {
                "non_null_count": sum(1 for r in records if r.get("word_count") is not None),
                "avg": (
                    sum(float(r["word_count"]) for r in records if isinstance(r.get("word_count"), (int, float)))
                    / max(1, sum(1 for r in records if isinstance(r.get("word_count"), (int, float))))
                ),
            },
        },
    }


def build_markdown(summary: Dict[str, Any]) -> str:
    tools = summary["tools_used"]
    fp = summary["failure_patterns"]
    lines = [
        "# Master Run Failure Analysis",
        "",
        f"- Runs analyzed: {summary['total_runs_analyzed']}",
        f"- Review rate: {summary['review_rate']:.2%}",
        "",
        "## Tools Used",
        f"- OCR tools: {json.dumps(tools['ocr_tools'], ensure_ascii=True)}",
        f"- Parse extraction methods: {json.dumps(tools['parse_extraction_methods'], ensure_ascii=True)}",
        f"- Parse models: {json.dumps(tools['parse_models'], ensure_ascii=True)}",
        "",
        "## OCR vs Parse Failure",
        f"- Parse failure by OCR bucket: {json.dumps(fp['parse_failure_rate_by_ocr_bucket'], ensure_ascii=True)}",
        f"- OCR vs parse matrix: {json.dumps(fp['ocr_vs_parse_matrix'], ensure_ascii=True)}",
        "",
        "## Top Failure Signals",
        f"- Issues: {json.dumps(fp['issue_counts'], ensure_ascii=True)}",
        f"- Reason codes: {json.dumps(fp['reason_code_counts'], ensure_ascii=True)}",
        "",
        "## High-OCR Parse-Failure Candidates",
    ]
    candidates = fp.get("high_ocr_parse_failure_candidates") or []
    if not candidates:
        lines.append("- None found.")
    else:
        for c in candidates[:10]:
            lines.append(
                f"- `{c['submission_id']}` conf={c['ocr_confidence_avg']:.3f} method={c['method']} reasons={','.join(c['reason_codes']) or 'n/a'}"
            )
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create master report across all artifact runs.")
    parser.add_argument("--artifacts-dir", default="artifacts", help="Artifacts root.")
    parser.add_argument("--out-dir", default=None, help="Output dir. Default artifacts/master_reports/<timestamp>.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    artifacts_dir = Path(args.artifacts_dir)
    if not artifacts_dir.is_absolute():
        artifacts_dir = (project_root / artifacts_dir).resolve()
    if not artifacts_dir.exists():
        raise SystemExit(f"Artifacts dir not found: {artifacts_dir}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir) if args.out_dir else artifacts_dir / "master_reports" / stamp
    if not out_dir.is_absolute():
        out_dir = (project_root / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    records = load_run_records(artifacts_dir)
    summary = build_summary(records)
    summary["run_info"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifacts_dir": str(artifacts_dir),
    }

    (out_dir / "master_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")
    (out_dir / "master_summary.md").write_text(build_markdown(summary), encoding="utf-8")
    (out_dir / "records_analyzed.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=True) + "\n" for r in records),
        encoding="utf-8",
    )
    print(f"Master report generated: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
