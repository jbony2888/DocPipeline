from __future__ import annotations

from typing import Tuple


def build_run_snapshot(summary: dict) -> dict:
    return {
        "review_rate_by_doc_type": summary.get("review_rate_by_doc_type", {}),
        "chunk_scoped_field_rate": summary.get("chunk_scoped_field_rate", 0),
        "chunk_scoped_field_from_start_rate": summary.get(
            "chunk_scoped_field_from_start_rate", 0
        ),
        "ocr_confidence_avg": summary.get("ocr_confidence_avg", 0),
        "reason_code_counts": summary.get("reason_code_counts", {}),
    }


def compare_snapshots(current: dict, baseline: dict) -> Tuple[bool, dict]:
    issues = []
    current_rr = current.get("review_rate_by_doc_type", {}) or {}
    baseline_rr = baseline.get("review_rate_by_doc_type", {}) or {}
    for doc_type, cvals in current_rr.items():
        c_rate = float(cvals.get("review_rate", 0))
        b_rate = float((baseline_rr.get(doc_type) or {}).get("review_rate", 0))
        if (c_rate - b_rate) > 0.10:
            issues.append(
                f"review_rate_by_doc_type[{doc_type}] increased by {c_rate - b_rate:.6f}"
            )

    c_chunk = float(current.get("chunk_scoped_field_rate", 0))
    b_chunk = float(baseline.get("chunk_scoped_field_rate", 0))
    if (b_chunk - c_chunk) > 0.03:
        issues.append(f"chunk_scoped_field_rate dropped by {b_chunk - c_chunk:.6f}")

    c_ocr = float(current.get("ocr_confidence_avg", 0))
    b_ocr = float(baseline.get("ocr_confidence_avg", 0))
    if (b_ocr - c_ocr) > 0.05:
        issues.append(f"ocr_confidence_avg dropped by {b_ocr - c_ocr:.6f}")

    c_reasons = set((current.get("reason_code_counts") or {}).keys())
    b_reasons = set((baseline.get("reason_code_counts") or {}).keys())
    new_reasons = sorted(c_reasons - b_reasons)
    if new_reasons:
        issues.append(f"new reason codes appeared: {new_reasons}")

    report = {"ok": len(issues) == 0, "issues": issues}
    return report["ok"], report

