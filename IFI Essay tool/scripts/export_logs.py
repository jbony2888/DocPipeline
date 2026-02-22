#!/usr/bin/env python3
"""
Export IFI operational logs + artifacts and generate normalized analytics datasets.

Default safety:
- PII is hashed unless --include-pii is passed.
- Raw essay text is excluded unless --include-text is passed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from dotenv import load_dotenv
from supabase import create_client

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from auth.supabase_client import normalize_supabase_url
from pipeline.supabase_storage import BUCKET_NAME


ARTIFACT_FILENAMES = (
    "analysis.json",
    "validation.json",
    "ocr_summary.json",
    "traceability.json",
    "extracted_fields.json",
    "pipeline_log.json",
)

TEXT_KEYS_BLOCKLIST = {
    "essay_text",
    "raw_text",
    "essay_block",
    "text",
    "lines",
}


def utc_now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def jsonl_write(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")


def hash_value(value: Optional[str], salt: str) -> Optional[str]:
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    return hashlib.sha256(f"{salt}:{v}".encode("utf-8")).hexdigest()


def hash_or_plain(value: Optional[str], include_pii: bool, salt: str) -> Optional[str]:
    if include_pii:
        return value
    return hash_value(value, salt)


def normalize_reason_codes(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        tokens = [str(x).strip().upper() for x in raw]
    else:
        text = str(raw).replace(",", ";")
        tokens = [x.strip().upper() for x in text.split(";")]
    return sorted(set([t for t in tokens if t]))


def safe_parse_json_bytes(raw_bytes: Optional[bytes]) -> Optional[Dict[str, Any]]:
    if not raw_bytes:
        return None
    try:
        return json.loads(raw_bytes.decode("utf-8"))
    except Exception:
        return None


def ocr_hist(values: Sequence[Optional[float]]) -> Dict[str, int]:
    bins = {
        "0.0-0.2": 0,
        "0.2-0.4": 0,
        "0.4-0.6": 0,
        "0.6-0.8": 0,
        "0.8-1.0": 0,
        "unknown": 0,
    }
    for v in values:
        if v is None:
            bins["unknown"] += 1
            continue
        if v < 0.2:
            bins["0.0-0.2"] += 1
        elif v < 0.4:
            bins["0.2-0.4"] += 1
        elif v < 0.6:
            bins["0.4-0.6"] += 1
        elif v < 0.8:
            bins["0.6-0.8"] += 1
        else:
            bins["0.8-1.0"] += 1
    return bins


def suspicious_student_name(name: Optional[str]) -> bool:
    if not name:
        return False
    t = str(name).strip()
    if not t:
        return False
    words = [w for w in re.split(r"\s+", t) if w]
    if len(words) > 5:
        return True
    verbs = {
        "is",
        "are",
        "was",
        "were",
        "be",
        "have",
        "has",
        "do",
        "did",
        "will",
        "can",
        "write",
        "wrote",
    }
    if any(w.lower().strip(".,!?") in verbs for w in words):
        return True
    alpha_words = [w for w in words if any(ch.isalpha() for ch in w)]
    if not alpha_words:
        return False
    titled = sum(1 for w in alpha_words if w[:1].isupper())
    return (titled / max(1, len(alpha_words))) < 0.4


def build_artifact_index_entry(
    submission_id: str,
    expected_files: Sequence[str],
    available_paths: Sequence[str],
) -> Dict[str, Any]:
    present = {name: any(p.endswith(f"/{name}") or p.endswith(name) for p in available_paths) for name in expected_files}
    missing = [name for name, ok in present.items() if not ok]
    return {
        "submission_id": submission_id,
        "expected_files": list(expected_files),
        "present_flags": present,
        "missing_files": missing,
        "artifact_missing": len(missing) > 0,
        "available_paths": list(available_paths),
    }


def get_admin_client():
    supabase_url = normalize_supabase_url(os.environ.get("SUPABASE_URL"))
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_key:
        return None
    return create_client(supabase_url, service_key)


def export_submissions_rows(
    sb,
    time_min: str,
    time_max: str,
    owner_user_id: Optional[str],
    max_submissions: Optional[int],
) -> List[Dict[str, Any]]:
    if sb is None:
        return []
    rows: List[Dict[str, Any]] = []
    page = 0
    page_size = 500
    while True:
        query = (
            sb.table("submissions")
            .select("*")
            .gte("created_at", time_min)
            .lte("created_at", time_max)
            .order("created_at", desc=False)
            .range(page * page_size, page * page_size + page_size - 1)
        )
        if owner_user_id:
            query = query.eq("owner_user_id", owner_user_id)
        try:
            data = query.execute().data or []
        except Exception:
            # Non-destructive export mode: if DB is unavailable, return what we have.
            break
        if not data:
            break
        rows.extend(data)
        if max_submissions and len(rows) >= max_submissions:
            rows = rows[:max_submissions]
            break
        if len(data) < page_size:
            break
        page += 1
    return rows


def write_csv_rows(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["submission_id"])
        return
    keys = sorted({k for row in rows for k in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def list_paths_recursive(sb, bucket: str, prefix: str) -> List[str]:
    paths: List[str] = []
    try:
        result = sb.storage.from_(bucket).list(prefix or None, {"limit": 1000})
    except Exception:
        return paths
    for item in result or []:
        name = item.get("name", "")
        if not name:
            continue
        full_path = f"{prefix}/{name}" if prefix else name
        try:
            children = sb.storage.from_(bucket).list(full_path, {"limit": 1})
            if children:
                paths.extend(list_paths_recursive(sb, bucket, full_path))
                continue
        except Exception:
            pass
        paths.append(full_path)
    return paths


def artifact_prefix_from_row(row: Dict[str, Any]) -> Optional[str]:
    artifact_dir = (row.get("artifact_dir") or "").strip()
    if not artifact_dir:
        return None
    if "/artifacts/" in artifact_dir:
        left, right = artifact_dir.split("/artifacts/", 1)
        run_id = right.split("/", 1)[0] if right else ""
        if run_id:
            return f"{left}/artifacts/{run_id}"
    return artifact_dir


def pick_paths(paths: Sequence[str], artifact_dir: str, prefix: str) -> List[str]:
    selected: List[str] = []
    for p in paths:
        if p.startswith(artifact_dir + "/") or p.startswith(prefix + "/"):
            if any(p.endswith("/" + name) or p.endswith(name) for name in ARTIFACT_FILENAMES):
                selected.append(p)
    return sorted(set(selected))


def parse_chunk_meta(path: str) -> Dict[str, Any]:
    m = re.search(r"/chunk_(\d+)_([0-9a-f]{12})/", path)
    if not m:
        return {"chunk_index": None, "chunk_submission_id": None}
    return {
        "chunk_index": int(m.group(1)),
        "chunk_submission_id": m.group(2),
    }


def pull_docker_logs(raw_dir: Path) -> Dict[str, Any]:
    docker_dir = ensure_dir(raw_dir / "docker_logs")
    out: Dict[str, Any] = {"mode": "docker", "ok": True, "files": []}
    for svc, filename in (("flask-app", "web.log"), ("worker", "worker.log")):
        target = docker_dir / filename
        cmd = ["docker", "compose", "logs", "--no-color", "--timestamps", svc]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            target.write_text(result.stdout or "", encoding="utf-8")
            out["files"].append(str(target))
            if result.returncode != 0:
                out["ok"] = False
                (docker_dir / f"{svc}.stderr.log").write_text(result.stderr or "", encoding="utf-8")
        except Exception as e:
            out["ok"] = False
            (docker_dir / f"{svc}.error.txt").write_text(str(e), encoding="utf-8")
    return out


def ingest_logs_from_files(log_dir: Path, out_jsonl: Path) -> int:
    rows: List[Dict[str, Any]] = []
    for path in sorted(log_dir.glob("**/*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".log", ".txt", ".jsonl"}:
            continue
        service = "worker" if "worker" in path.name.lower() else "web"
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                text = line.rstrip("\n")
                if not text.strip():
                    continue
                ts_match = re.search(r"(\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)?)", text)
                job_match = re.search(r"job_id=([a-zA-Z0-9\-]+)", text)
                sub_match = re.search(r"submission_id=([0-9a-f]{12})", text)
                filename_match = re.search(r"filename=([^\s]+)", text)
                level = "ERROR" if "ERROR" in text or "FAILED" in text else ("WARNING" if "WARN" in text else "INFO")
                rows.append(
                    {
                        "timestamp": ts_match.group(1) if ts_match else None,
                        "service": service,
                        "level": level,
                        "job_id": job_match.group(1) if job_match else None,
                        "submission_id": sub_match.group(1) if sub_match else None,
                        "filename": filename_match.group(1) if filename_match else None,
                        "message": text,
                    }
                )
    jsonl_write(out_jsonl, rows)
    return len(rows)


def compute_summary_metrics(
    submissions: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    artifacts_health: List[Dict[str, Any]],
) -> Dict[str, Any]:
    by_doc = Counter((r.get("doc_class") or "UNKNOWN") for r in submissions)
    by_reason = Counter()
    review_count = Counter()
    total_by_doc = Counter()
    reason_pairs = Counter()
    by_format_ocr_avg: Dict[str, List[Optional[float]]] = defaultdict(list)
    by_format_ocr_min: Dict[str, List[Optional[float]]] = defaultdict(list)
    by_format_ocr_p10: Dict[str, List[Optional[float]]] = defaultdict(list)
    false_empty = 0
    empty_total = 0
    suspicious_name_count = 0
    parent_chunks: Dict[str, int] = defaultdict(int)
    parent_pages: Dict[str, Optional[int]] = {}
    chunks_missing_any = 0

    for r in submissions:
        doc_class = r.get("doc_class") or "UNKNOWN"
        total_by_doc[doc_class] += 1
        if r.get("needs_review"):
            review_count[doc_class] += 1
        reasons = r.get("reason_codes", [])
        for code in reasons:
            by_reason[code] += 1
        for a, b in itertools.combinations(sorted(set(reasons)), 2):
            reason_pairs[(a, b)] += 1
        fmt = r.get("format") or "unknown"
        by_format_ocr_avg[fmt].append(r.get("ocr_conf_avg"))
        by_format_ocr_min[fmt].append(r.get("ocr_conf_min"))
        by_format_ocr_p10[fmt].append(r.get("ocr_conf_p10"))
        if "EMPTY_ESSAY" in reasons:
            empty_total += 1
            char_count = r.get("ocr_char_count") or 0
            conf = r.get("ocr_conf_avg")
            if char_count > 200 or (conf is not None and conf >= 0.7):
                false_empty += 1
        if suspicious_student_name(r.get("_student_name_raw_for_metrics")):
            suspicious_name_count += 1
        parent_id = r.get("parent_submission_id") or r.get("submission_id")
        parent_chunks[parent_id] += 1
        parent_pages[parent_id] = r.get("page_count")

    for c in chunks:
        if c.get("artifact_missing"):
            chunks_missing_any += 1

    review_rate_by_doc = {
        k: (review_count[k] / total_by_doc[k] if total_by_doc[k] else 0.0)
        for k in sorted(total_by_doc.keys())
    }

    top_pairs = [
        {"pair": [a, b], "count": count}
        for (a, b), count in reason_pairs.most_common(20)
    ]

    chunk_counts = list(parent_chunks.values())
    multi_parent_count = sum(1 for n in chunk_counts if n > 1)
    multi_rate = (multi_parent_count / len(chunk_counts)) if chunk_counts else 0.0
    chunk_dist = dict(sorted(Counter(chunk_counts).items()))

    long_bundle_ratios: List[float] = []
    for parent_id, ccount in parent_chunks.items():
        pages = parent_pages.get(parent_id)
        if pages and pages >= 6 and ccount >= 4:
            long_bundle_ratios.append(pages / ccount)
    oversplitting_indicator = {
        "avg_pages_per_chunk_long_bundles": (sum(long_bundle_ratios) / len(long_bundle_ratios)) if long_bundle_ratios else None,
        "candidate": bool(long_bundle_ratios) and (sum(long_bundle_ratios) / len(long_bundle_ratios)) <= 1.2,
    }

    artifacts_missing_rate = (
        sum(1 for a in artifacts_health if a.get("artifact_missing")) / len(artifacts_health)
        if artifacts_health
        else 0.0
    )

    return {
        "counts_by_doc_class": dict(by_doc),
        "review_rate_by_doc_class": review_rate_by_doc,
        "reason_code_counts": dict(by_reason),
        "top_reason_pairs": top_pairs,
        "ocr_confidence_histograms": {
            fmt: {
                "avg": ocr_hist(by_format_ocr_avg[fmt]),
                "min": ocr_hist(by_format_ocr_min[fmt]),
                "p10": ocr_hist(by_format_ocr_p10[fmt]),
            }
            for fmt in sorted(set(list(by_format_ocr_avg.keys()) + list(by_format_ocr_min.keys()) + list(by_format_ocr_p10.keys())))
        },
        "multi_chunk_stats": {
            "multi_detection_rate": multi_rate,
            "chunk_count_distribution": chunk_dist,
            "total_parents": len(chunk_counts),
        },
        "artifacts_missing_rate": artifacts_missing_rate,
        "false_empty_essay_rate": (false_empty / empty_total) if empty_total else 0.0,
        "suspicious_student_name_rate": (suspicious_name_count / len(submissions)) if submissions else 0.0,
        "oversplitting_indicator": oversplitting_indicator,
    }


def build_summary_md(summary: Dict[str, Any]) -> str:
    doc_counts = summary.get("counts_by_doc_class", {})
    reason_counts = summary.get("reason_code_counts", {})
    top_reasons = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    lines = [
        "# IFI Processing Pattern Report",
        "",
        "## Intake Profile",
        f"- Total classified submissions: {sum(doc_counts.values())}",
        f"- Document class mix: {json.dumps(doc_counts, ensure_ascii=True)}",
        "",
        "## Top Failure Patterns",
    ]
    if top_reasons:
        for code, count in top_reasons:
            lines.append(f"- {code}: {count}")
    else:
        lines.append("- No reason-code failures observed in this window.")
    lines.extend(
        [
            "",
            "## Key Risk Signals",
            f"- Artifacts missing rate: {summary.get('artifacts_missing_rate', 0.0):.2%}",
            f"- False EMPTY_ESSAY candidate rate: {summary.get('false_empty_essay_rate', 0.0):.2%}",
            f"- Suspicious student_name rate: {summary.get('suspicious_student_name_rate', 0.0):.2%}",
            "",
            "## Ranked Next Improvements",
            "1. Reduce top two review reason codes with targeted extraction/validation fixes.",
            "2. Improve artifact write guarantees (analysis + validation + traceability completeness).",
            "3. Tune EMPTY_ESSAY logic using OCR confidence and page char-count guardrails.",
            "4. Review chunking thresholds where pages-per-chunk is near 1.0 on long bundles.",
            "",
            "_Client-safe: no raw essay text or plain PII included._",
        ]
    )
    return "\n".join(lines) + "\n"


def normalize_records(
    rows: List[Dict[str, Any]],
    artifact_payloads: Dict[str, Dict[str, Dict[str, Any]]],
    artifact_index_rows: List[Dict[str, Any]],
    include_pii: bool,
    include_text: bool,
    salt: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    index_by_submission = {r["submission_id"]: r for r in artifact_index_rows}
    submissions: List[Dict[str, Any]] = []
    chunks: List[Dict[str, Any]] = []
    health_rows: List[Dict[str, Any]] = []

    for row in rows:
        submission_id = row.get("submission_id")
        if not submission_id:
            continue
        payload = artifact_payloads.get(submission_id, {})
        analysis = payload.get("analysis.json") or {}
        validation = payload.get("validation.json") or {}
        ocr = payload.get("ocr_summary.json") or {}
        traceability = payload.get("traceability.json") or {}
        extracted = payload.get("extracted_fields.json") or {}
        pipeline_log = payload.get("pipeline_log.json") or {}

        reasons = normalize_reason_codes(
            validation.get("review_reason_codes")
            or validation.get("issues")
            or row.get("review_reason_codes")
        )
        artifact_flags = (index_by_submission.get(submission_id) or {}).get("present_flags", {})

        student_name_raw = extracted.get("student_name", row.get("student_name"))
        school_name_raw = extracted.get("school_name", row.get("school_name"))
        grade_raw = extracted.get("grade", row.get("grade"))

        doc = {
            "submission_id": submission_id,
            "filename": row.get("filename"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "owner_user_id_hash": hash_value(str(row.get("owner_user_id") or ""), salt),
            "doc_class": row.get("doc_class") or analysis.get("doc_class"),
            "format": row.get("format") or analysis.get("format"),
            "structure": row.get("structure") or analysis.get("structure"),
            "form_layout": row.get("form_layout") or analysis.get("form_layout"),
            "page_count": analysis.get("page_count"),
            "chunk_count": len(analysis.get("chunk_ranges") or []),
            "ocr_provider": None,
            "llm_provider": None,
            "prompt_version": None,
            "classifier_version": analysis.get("classifier_version"),
            "ocr_conf_avg": ocr.get("confidence_avg", row.get("ocr_confidence_avg")),
            "ocr_conf_min": ocr.get("confidence_min"),
            "ocr_conf_p10": ocr.get("confidence_p10"),
            "low_conf_page_count": ocr.get("low_conf_page_count"),
            "ocr_char_count": ocr.get("char_count"),
            "has_student_name": bool(student_name_raw),
            "has_grade": bool(grade_raw is not None and str(grade_raw).strip() != ""),
            "has_school": bool(school_name_raw),
            "needs_review": bool(row.get("needs_review")),
            "reason_codes": reasons,
            "parent_submission_id": (
                traceability.get("parent_submission_id")
                or row.get("parent_submission_id")
                or submission_id
            ),
            "artifact_present": {
                "analysis": bool(artifact_flags.get("analysis.json")),
                "validation": bool(artifact_flags.get("validation.json")),
                "ocr_summary": bool(artifact_flags.get("ocr_summary.json")),
                "traceability": bool(artifact_flags.get("traceability.json")),
                "extracted_fields": bool(artifact_flags.get("extracted_fields.json")),
            },
            "artifact_missing": bool((index_by_submission.get(submission_id) or {}).get("artifact_missing")),
            "processing_durations": {},
            "_student_name_raw_for_metrics": student_name_raw,
        }

        # Infer providers from pipeline log model naming.
        model_name = str((pipeline_log.get("extraction_debug") or {}).get("model") or "")
        if "groq" in model_name.lower():
            doc["llm_provider"] = "groq"
        elif model_name:
            doc["llm_provider"] = "other"

        if include_pii:
            doc["student_name"] = student_name_raw
            doc["school_name"] = school_name_raw
        else:
            doc["student_name_hash"] = hash_or_plain(student_name_raw, include_pii=False, salt=salt)
            doc["school_name_hash"] = hash_or_plain(school_name_raw, include_pii=False, salt=salt)

        if include_text:
            for key in TEXT_KEYS_BLOCKLIST:
                if key in extracted:
                    doc[key] = extracted.get(key)

        submissions.append(doc)

        chunk = {
            "parent_submission_id": traceability.get("parent_submission_id") or doc["parent_submission_id"],
            "chunk_submission_id": traceability.get("chunk_submission_id") or submission_id,
            "chunk_index": traceability.get("chunk_index"),
            "page_start": traceability.get("chunk_page_start"),
            "page_end": traceability.get("chunk_page_end"),
            "has_student_name": doc["has_student_name"],
            "has_school": doc["has_school"],
            "has_grade": doc["has_grade"],
            "chunk_reason_codes": reasons,
            "ocr_conf_avg": doc["ocr_conf_avg"],
            "ocr_conf_min": doc["ocr_conf_min"],
            "ocr_conf_p10": doc["ocr_conf_p10"],
            "field_source_pages_coverage_rate": None,
            "artifact_missing": doc["artifact_missing"],
        }
        chunks.append(chunk)

        health_rows.append(
            {
                "submission_id": submission_id,
                "artifact_missing": doc["artifact_missing"],
                "present_flags": artifact_flags,
                "missing_files": (index_by_submission.get(submission_id) or {}).get("missing_files", []),
            }
        )

    return submissions, chunks, health_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export IFI logs + artifacts and generate analytics datasets.")
    parser.add_argument("--time-min", required=True, help="ISO timestamp inclusive lower bound.")
    parser.add_argument("--time-max", required=True, help="ISO timestamp inclusive upper bound.")
    parser.add_argument("--owner-user-id", default=None, help="Optional owner_user_id filter.")
    parser.add_argument("--out-dir", default=None, help="Output directory. Default artifacts/log_exports/<timestamp>.")
    parser.add_argument("--include-pii", action="store_true", help="Include plain student_name/school_name.")
    parser.add_argument("--include-text", action="store_true", help="Include raw text fields (off by default).")
    parser.add_argument("--max-submissions", type=int, default=None, help="Optional cap for sampling.")
    parser.add_argument("--log-source", choices=["auto", "docker", "render", "files"], default="auto")
    parser.add_argument("--log-dir", default=None, help="Directory with previously exported logs (local ingest mode).")
    parser.add_argument("--render-web-service-id", default=None)
    parser.add_argument("--render-worker-service-id", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")

    if not args.include_text:
        pass  # Explicitly preserve default safety behavior.

    out_dir = Path(args.out_dir) if args.out_dir else project_root / "artifacts" / "log_exports" / utc_now_slug()
    if not out_dir.is_absolute():
        out_dir = (project_root / out_dir).resolve()
    raw_dir = ensure_dir(out_dir / "raw")
    ensure_dir(out_dir / "normalized")
    ensure_dir(out_dir / "reports")
    ensure_dir(raw_dir / "artifacts")

    salt = os.environ.get("EXPORT_HASH_SALT", "ifi-export-default-salt")

    # Logs
    logs_meta: Dict[str, Any] = {"mode": "none", "ok": True}
    logs_jsonl = raw_dir / "ingested_logs.jsonl"
    if args.log_source in ("auto", "docker"):
        logs_meta = pull_docker_logs(raw_dir)
    if args.log_source == "files" and args.log_dir:
        logs_meta = {"mode": "files", "ok": True}
    if args.log_source == "render":
        render_dir = ensure_dir(raw_dir / "render_logs")
        guidance = [
            "Render API log pull is environment-dependent.",
            "If direct API access is unavailable, export logs from Render UI and ingest them with:",
            "python scripts/ingest_logs_from_files.py --log-dir <exported-log-dir> --out-jsonl <target>",
            f"Expected service IDs (optional): web={args.render_web_service_id}, worker={args.render_worker_service_id}",
        ]
        (render_dir / "README_RENDER_LOG_EXPORT.txt").write_text("\n".join(guidance) + "\n", encoding="utf-8")
        logs_meta = {"mode": "render", "ok": False, "note": "Created local ingest guidance file."}

    if args.log_dir:
        ingested_count = ingest_logs_from_files(Path(args.log_dir), logs_jsonl)
        logs_meta["ingested_log_rows"] = ingested_count
    elif logs_meta.get("mode") == "docker":
        docker_dir = raw_dir / "docker_logs"
        ingested_count = ingest_logs_from_files(docker_dir, logs_jsonl)
        logs_meta["ingested_log_rows"] = ingested_count
    else:
        jsonl_write(logs_jsonl, [])
        logs_meta["ingested_log_rows"] = 0

    # DB
    sb = get_admin_client()
    rows = export_submissions_rows(sb, args.time_min, args.time_max, args.owner_user_id, args.max_submissions)
    write_csv_rows(raw_dir / "db_submissions.csv", rows)

    artifact_index_rows: List[Dict[str, Any]] = []
    artifact_payloads: Dict[str, Dict[str, Dict[str, Any]]] = {}

    # Storage artifacts
    for row in rows:
        submission_id = row.get("submission_id")
        if not submission_id:
            continue
        artifact_dir = (row.get("artifact_dir") or "").strip()
        prefix = artifact_prefix_from_row(row) or artifact_dir
        paths: List[str] = []
        if sb is not None and prefix:
            paths = list_paths_recursive(sb, BUCKET_NAME, prefix)
        selected = pick_paths(paths, artifact_dir, prefix) if artifact_dir else []
        idx_entry = build_artifact_index_entry(submission_id, ARTIFACT_FILENAMES, selected)
        idx_entry["artifact_dir"] = artifact_dir
        idx_entry["artifact_prefix"] = prefix
        artifact_index_rows.append(idx_entry)

        per_submission_payload: Dict[str, Dict[str, Any]] = {}
        local_submission_dir = ensure_dir(raw_dir / "artifacts" / submission_id)
        for storage_path in selected:
            rel_name = storage_path.replace("/", "__")
            local_path = local_submission_dir / rel_name
            parsed = None
            if sb is not None:
                try:
                    b = sb.storage.from_(BUCKET_NAME).download(storage_path)
                    local_path.write_bytes(b)
                    parsed = safe_parse_json_bytes(b)
                except Exception:
                    parsed = None
            filename = storage_path.rsplit("/", 1)[-1]
            if parsed is not None:
                # Keep last one for each filename in memory payload map.
                per_submission_payload[filename] = parsed
        artifact_payloads[submission_id] = per_submission_payload

    jsonl_write(raw_dir / "storage_artifacts_index.jsonl", artifact_index_rows)

    submissions_norm, chunks_norm, health_norm = normalize_records(
        rows=rows,
        artifact_payloads=artifact_payloads,
        artifact_index_rows=artifact_index_rows,
        include_pii=args.include_pii,
        include_text=args.include_text,
        salt=salt,
    )

    # Remove internal metric-only fields before writing.
    for r in submissions_norm:
        r.pop("_student_name_raw_for_metrics", None)

    jsonl_write(out_dir / "normalized" / "submissions_normalized.jsonl", submissions_norm)
    jsonl_write(out_dir / "normalized" / "chunks_normalized.jsonl", chunks_norm)
    jsonl_write(out_dir / "normalized" / "artifacts_health.jsonl", health_norm)

    summary = compute_summary_metrics(
        submissions=[
            {**r, "_student_name_raw_for_metrics": (artifact_payloads.get(r["submission_id"], {}).get("extracted_fields.json", {}) or {}).get("student_name", row.get("student_name") if (row := next((x for x in rows if x.get("submission_id") == r["submission_id"]), {})) else None)}
            for r in submissions_norm
        ],
        chunks=chunks_norm,
        artifacts_health=health_norm,
    )
    summary["run_info"] = {
        "time_min": args.time_min,
        "time_max": args.time_max,
        "owner_user_id_filter": args.owner_user_id,
        "rows_exported": len(rows),
        "log_meta": logs_meta,
        "out_dir": str(out_dir),
        "include_pii": bool(args.include_pii),
        "include_text": bool(args.include_text),
    }
    write_json(out_dir / "reports" / "summary.json", summary)
    (out_dir / "reports" / "summary.md").write_text(build_summary_md(summary), encoding="utf-8")
    write_json(out_dir / "reports" / "run_meta.json", logs_meta)

    print(f"Export complete: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
