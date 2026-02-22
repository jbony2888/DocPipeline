"""
Lightweight regression harness for document analysis hardening.

Runs four scenario checks:
1) Multi-submission bundle
2) Template-only IFI form
3) Single scanned handwriting
4) Hybrid (synthetic) mixed text/image

Supports:
- Stub/real OCR providers for offline/online runs.
- Legacy page-1-only simulation for apples-to-apples comparison.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Tuple

import fitz  # PyMuPDF

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from pipeline.document_analysis import analyze_document, ChunkRange
from pipeline.runner import process_submission
from pipeline.ocr import ocr_pdf_pages, extract_pdf_text_layer
from pipeline.extract import looks_like_essay_fragment
from pipeline.doc_type_routing import detect_pdf_has_acroform_fields, route_doc_type
from pipeline.guardrails.attribution import (
    assert_expected_attribution,
    build_field_attribution_debug_payload,
    compute_field_attribution_confidence,
    compute_field_source_pages,
    load_per_page_text,
)
from pipeline.guardrails.drift import build_run_snapshot, compare_snapshots
from pipeline.guardrails.doc_role import DocRole, classify_doc_role
from pipeline.guardrails.enums import ALLOWED_REASON_CODES


def generate_hybrid_fixture(tmpdir: Path) -> Path:
    """Create a small two-page hybrid PDF (page1 text layer, page2 image)."""
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text((72, 72), "Hybrid Header\nStudent Name: Hybrid Test\nGrade: 6")

    # Render page1 to image for page2
    pix = page1.get_pixmap(dpi=200)
    png_bytes = pix.tobytes("png")
    page2 = doc.new_page()
    page2.insert_image(page2.rect, stream=png_bytes)

    out_path = tmpdir / "hybrid_fixture.pdf"
    doc.save(out_path)
    doc.close()
    return out_path


def generate_scanned_fixture(tmpdir: Path) -> Path:
    """Create an image-only PDF by rasterizing a text page."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Handwritten style (synthetic)\nSchool: Sample School\nGrade: 7")
    pix = page.get_pixmap(dpi=200)
    png_bytes = pix.tobytes("png")
    doc_img = fitz.open()
    page_img = doc_img.new_page()
    page_img.insert_image(page_img.rect, stream=png_bytes)
    out_path = tmpdir / "scanned_fixture.pdf"
    doc_img.save(out_path)
    doc.close()
    doc_img.close()
    return out_path


def generate_multi_fixture(tmpdir: Path) -> Path:
    """Create a synthetic multi-submission PDF with two distinct headers."""
    doc = fitz.open()
    # First submission
    p1 = doc.new_page()
    p1.insert_text((72, 72), "IFI Fatherhood Essay Contest\nStudent Name: First Student\nGrade: 6\nSchool: Lincoln")
    p1.insert_text((72, 140), "Essay body page 1.\nMore essay text.")
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Essay body page 2 continuing.")
    # Second submission
    p3 = doc.new_page()
    p3.insert_text((72, 72), "IFI Fatherhood Essay Contest\nStudent Name: Second Student\nGrade: 8\nSchool: Carson")
    p3.insert_text((72, 140), "Second essay body page 1.")
    out_path = tmpdir / "multi_fixture.pdf"
    doc.save(out_path)
    doc.close()
    return out_path


def chunk_paths(pdf_path: Path, chunks: List[ChunkRange], tmpdir: Path) -> List[Tuple[int, Path]]:
    """Split PDF into per-chunk temporary PDFs."""
    doc = fitz.open(pdf_path)
    results: List[Tuple[int, Path]] = []
    for idx, c in enumerate(chunks):
        chunk_doc = fitz.open()
        chunk_doc.insert_pdf(doc, from_page=c.start_page, to_page=c.end_page, widgets=0)
        out_path = tmpdir / f"chunk_{idx}.pdf"
        chunk_doc.save(out_path)
        results.append((idx, out_path))
    doc.close()
    return results


GRADE_PATTERNS = [
    # "Grade / Grado: 5" or "Grade: 5" (label-followed, official form placement)
    r"(?im)\b(?:grade|grado)\s*[:\-]?\s*(pre[\s\-]?k|k|[0-9]{1,2})\b",
    # "6th grade" or "6th Grade" (inline with school, header placement)
    r"(?im)\b([1-9]|1[0-2])(?:st|nd|rd|th)?\s*grade\b",
    # "Grade 6" or "Grado 6" (value after label on same line)
    r"(?im)(?:grade|grado)\s+([1-9]|1[0-2])\b",
    # "3rd Grade" in header (comma-separated: "Name, School, 3rd Grade" or line end)
    r"(?im)(?:^|[,/\-])\s*([1-9]|1[0-2])(?:st|nd|rd|th)?\s*grade\b",
]
SCHOOL_PATTERNS = [
    r"(?im)\b(?:school(?:\s+name)?|campus|escuela)\s*[:\-]?\s*([^\n\r]{2,120})",
]


def _clip_snippet(text: str, max_chars: int = 300, max_lines: int = 20) -> str:
    lines = (text or "").splitlines()[:max_lines]
    snippet = "\n".join(lines).strip()
    return snippet[:max_chars]


def build_chunk_submission_id(parent_submission_id: str, chunk_index: int, original_filename: str) -> str:
    """
    Build a collision-resistant chunk submission id namespaced by parent submission id.
    Prevents same-filename collisions across different documents.
    """
    suffix = hashlib.sha256(
        f"{parent_submission_id}:{original_filename}:{chunk_index}".encode("utf-8")
    ).hexdigest()[:8]
    return f"{parent_submission_id}_{chunk_index}_{suffix}"


def _is_valid_grade_value(val: str) -> bool:
    """Reject grades outside 1-12. Only 1-12 and K are valid."""
    if not val or not val.strip():
        return False
    v = val.strip().upper()
    if v in ("K", "KINDER", "KINDERGARTEN", "PRE-K", "PREK"):
        return True
    try:
        n = int(v)
        return 1 <= n <= 12
    except ValueError:
        # Ordinals like "6th"
        m = re.search(r"(\d+)(?:st|nd|rd|th)?", v, re.IGNORECASE)
        if m:
            return 1 <= int(m.group(1)) <= 12
        return False


def extract_doc_fields_from_final_text(final_text: str) -> Dict[str, str | None]:
    """Extract doc-level school/grade from OCR-aggregated final text."""
    extracted: Dict[str, str | None] = {"student_name": None, "grade": None, "school_name": None}

    for pattern in GRADE_PATTERNS:
        match = re.search(pattern, final_text or "")
        if match:
            raw = match.group(1).strip()
            if _is_valid_grade_value(raw):
                extracted["grade"] = raw
            break

    for pattern in SCHOOL_PATTERNS:
        match = re.search(pattern, final_text or "")
        if match:
            school = re.sub(r"\s+", " ", match.group(1)).strip(" .,:;-\t")
            # Reject essay text captured after "School"/"Escuela" (e.g. "and if anything")
            if school and not looks_like_essay_fragment(school):
                extracted["school_name"] = school
            if extracted.get("school_name"):
                break

    return extracted


def aggregate_parent_status_from_children(chunk_diagnostics: List[dict]) -> tuple[bool, set[str]]:
    """
    Derive parent needs_review and reason_codes from children using logical OR.
    Ensures parent never shows clean when any child has errors.
    """
    if not chunk_diagnostics:
        return False, set()
    needs_review = any(d.get("chunk_needs_review", False) for d in chunk_diagnostics)
    reason_codes: set[str] = set()
    for d in chunk_diagnostics:
        codes = d.get("chunk_reason_codes") or []
        if isinstance(codes, str):
            codes = [c.strip() for c in codes.split(";") if c.strip()]
        reason_codes.update(codes)
    return needs_review, reason_codes


def apply_doc_review_metrics(
    summary: dict,
    *,
    doc_role: DocRole,
    doc_type: str,
    doc_needs_review: bool,
    doc_reason_codes: set[str],
    failures: list[str],
    pdf_name: str,
) -> None:
    """
    Apply review-related counters while excluding container docs.
    """
    if doc_role == DocRole.CONTAINER:
        summary["container_docs_count"] += 1
        summary["skipped_container_docs"] += 1
        return

    summary["total_docs"] += 1
    if doc_needs_review:
        summary["docs_reviewed_count"] += 1
    else:
        summary["auto_approved_count"] += 1

    for code in doc_reason_codes:
        summary["reason_code_counts"][code] = summary["reason_code_counts"].get(code, 0) + 1
        if "=" in code or code not in ALLOWED_REASON_CODES:
            failures.append(f"Reason code not enum: {code} ({pdf_name})")
        if code == "PENDING_REVIEW":
            failures.append(f"Forbidden reason code PENDING_REVIEW found ({pdf_name})")
    if "OCR_LOW_CONFIDENCE" in doc_reason_codes:
        summary["ocr_low_confidence_docs"] += 1
    if "EMPTY_ESSAY" in doc_reason_codes:
        summary["false_empty_essay_count"] += 1

    type_bucket = summary["review_rate_by_doc_type"].setdefault(
        doc_type, {"total": 0, "needs_review": 0, "review_rate": 0}
    )
    type_bucket["total"] += 1
    if doc_needs_review:
        type_bucket["needs_review"] += 1


def _normalize_reason_codes(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(";")]
    elif isinstance(value, list):
        parts = [str(p).strip() for p in value]
    else:
        parts = [str(value).strip()]
    return [p for p in parts if p]


def compute_doc_reason_codes(
    *,
    extracted: Dict[str, str | None],
    final_text: str,
    submission_id: str,
    is_template_doc: bool,
    template_blocked_low_conf: bool,
) -> tuple[set[str], Dict[str, Dict]]:
    """
    Compute doc-level reason codes from OCR aggregate text with template short-circuit.
    Returns (reason_codes, missing_field_evidence).
    """
    reason_codes: set[str] = set()
    evidence: Dict[str, Dict] = {}

    if is_template_doc:
        reason_codes.add("TEMPLATE_ONLY")
        if template_blocked_low_conf:
            reason_codes.add("OCR_LOW_CONFIDENCE")
        return reason_codes, evidence

    if template_blocked_low_conf:
        reason_codes.add("OCR_LOW_CONFIDENCE")

    if not extracted.get("grade"):
        reason_codes.add("MISSING_GRADE")
        evidence["grade"] = {
            "source": "final_text_ocr_aggregate",
            "patterns": GRADE_PATTERNS,
            "match": None,
            "snippet": _clip_snippet(final_text),
            "doc_id": submission_id,
            "submission_id": submission_id,
        }
    if not extracted.get("school_name"):
        reason_codes.add("MISSING_SCHOOL_NAME")
        evidence["school_name"] = {
            "source": "final_text_ocr_aggregate",
            "patterns": SCHOOL_PATTERNS,
            "match": None,
            "snippet": _clip_snippet(final_text),
            "doc_id": submission_id,
            "submission_id": submission_id,
        }
    return reason_codes, evidence


def run_chunk_pipeline(
    chunk_idx: int,
    chunk_path: Path,
    parent_id: str,
    original_filename: str,
    doc_format: str,
    template_flag: bool,
    ocr_provider_name: str,
    chunk_page_start: int | None = None,
    chunk_page_end: int | None = None,
    template_blocked_low_conf: bool = False,
    doc_class=None,
    analysis_structure: str | None = None,
    analysis_form_layout: str | None = None,
    analysis_header_signature_score_max: float | None = None,
):
    """Process a single chunk through the pipeline runner using selected OCR provider."""
    submission_id = build_chunk_submission_id(parent_id, chunk_idx, original_filename)
    meta = {
        "parent_submission_id": parent_id,
        "chunk_index": chunk_idx,
        "chunk_page_start": chunk_page_start,
        "chunk_page_end": chunk_page_end,
        "is_chunk": True,
        "template_detected": template_flag,
        "template_blocked_low_confidence": template_blocked_low_conf,
    }
    if doc_class is not None:
        meta["doc_class"] = doc_class
    if analysis_structure is not None:
        meta["analysis_structure"] = analysis_structure
    if analysis_form_layout is not None:
        meta["analysis_form_layout"] = analysis_form_layout
    if analysis_header_signature_score_max is not None:
        meta["analysis_header_signature_score_max"] = analysis_header_signature_score_max
    record, report = process_submission(
        image_path=str(chunk_path),
        submission_id=submission_id,
        artifact_dir=f"local/{parent_id}/{submission_id}",
        ocr_provider_name=ocr_provider_name,
        original_filename=original_filename,
        chunk_metadata=meta,
        doc_format=doc_format,
    )
    return record, report


class LowConfProvider:
    """Fake OCR provider that returns boilerplate text with very low confidence."""

    def process_image(self, image_path: str):
        from pipeline.schema import OcrResult
        txt = "IFI Fatherhood Essay Contest\nStudent Name:\nGrade / Grado:\nSchool / Escuela:"
        return OcrResult(
            text=txt,
            confidence_avg=0.1,
            confidence_min=0.1,
            confidence_p10=0.1,
            low_conf_page_count=1,
            lines=txt.splitlines()
        )


def compute_submission_id(pdf_path: Path) -> str:
    """Deterministic submission id from file bytes."""
    with open(pdf_path, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest()
    return h[:12]


# Expected reason codes for typed-form test cases with one required field missing (flag for review, never fail).
TYPED_FORM_MISSING_FIELD_EXPECTATIONS = {
    "tc06_standard_form_missing_grade.pdf": "MISSING_GRADE",
    "tc07_standard_form_missing_student_name.pdf": "MISSING_STUDENT_NAME",
    "tc08_standard_form_missing_school_name.pdf": "MISSING_SCHOOL_NAME",
}


def validate_typed_form_missing_field_expectations(
    pdf_paths: List[Path], docs_dir: Path
) -> List[str]:
    """
    When running the 8 typed-form tc PDFs: assert missing-field cases are flagged for review,
    not failed, and every doc produced a record (so a human can fill in missing data).
    """
    failures: List[str] = []
    if len(pdf_paths) != 8:
        return failures
    names = [p.name for p in pdf_paths]
    if not all(re.match(r"tc0[1-8]_.*\.pdf", n) for n in names):
        return failures

    reviewed = 0
    auto = 0
    for pdf_path in pdf_paths:
        submission_id = compute_submission_id(pdf_path)
        summary_path = docs_dir / submission_id / "doc_summary.json"
        if not summary_path.exists():
            failures.append(
                f"Typed-form doc must not fail: no record produced for {pdf_path.name} (expected record for human review)."
            )
            continue
        with open(summary_path, "r", encoding="utf-8") as f:
            doc_summary = json.load(f)
        filename = doc_summary.get("filename", "")
        chunk_count = doc_summary.get("chunk_count", 0)
        needs_review = doc_summary.get("needs_review", False)
        reason_codes = doc_summary.get("reason_codes") or []
        doc_type = doc_summary.get("doc_type")
        if doc_type != "ifi_typed_form_submission":
            failures.append(
                f"Typed-form case must route to ifi_typed_form_submission: {filename} got {doc_type}."
            )
        if needs_review:
            reviewed += 1
        else:
            auto += 1

        if chunk_count < 1:
            failures.append(
                f"Typed-form doc must produce a record: {filename} has chunk_count={chunk_count} (needs review, not fail)."
            )
        expected_code = TYPED_FORM_MISSING_FIELD_EXPECTATIONS.get(filename)
        if expected_code:
            if not needs_review:
                failures.append(
                    f"Missing-field case must be flagged for review: {filename} has needs_review=false (human must fill in missing data)."
                )
            if expected_code not in reason_codes:
                failures.append(
                    f"Missing-field case must have reason code {expected_code}: {filename} has reason_codes={reason_codes}."
                )

    if auto != 5 or reviewed != 3:
        failures.append(
            f"Typed-form expectation mismatch: expected auto_approved_count=5 and docs_reviewed_count=3, got {auto} and {reviewed}."
        )

    return failures


def has_multiple_header_peaks(analysis) -> bool:
    """Heuristic: detect at least two local header-score peaks above threshold."""
    scores = [p.header_signature_score for p in analysis.pages]
    if len(scores) < 2:
        return False
    peaks = 0
    for idx, score in enumerate(scores):
        if score < 0.2:
            continue
        left = scores[idx - 1] if idx > 0 else -1.0
        right = scores[idx + 1] if idx + 1 < len(scores) else -1.0
        if score >= left and score >= right:
            peaks += 1
    return peaks >= 2


def write_field_attribution_debug_artifact(
    *,
    chunk_artifact_dir: Path,
    submission_id: str,
    chunk_submission_id: str,
    doc_type: str,
    chunk_page_start: int,
    chunk_page_end: int,
    extracted_fields: dict,
    field_source_pages: dict,
    per_page_text: list[dict],
) -> bool:
    payload = build_field_attribution_debug_payload(
        submission_id=submission_id,
        chunk_submission_id=chunk_submission_id,
        doc_type=doc_type,
        chunk_page_start=chunk_page_start,
        chunk_page_end=chunk_page_end,
        extracted_fields=extracted_fields,
        field_source_pages=field_source_pages,
        per_page_text=per_page_text,
    )
    if payload is None:
        return False
    with open(chunk_artifact_dir / "field_attribution_debug.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return True


def enforce_attribution_thresholds(
    attribution_counts_by_doc_type: dict[str, dict[str, int]],
    output_dir: Path,
) -> List[str]:
    """
    Enforce attribution rate thresholds by doc type.
    """
    failures: List[str] = []
    thresholds = {
        "ifi_typed_form_submission": {"within": 0.95, "from_start": 0.95},
        "bulk_scanned_batch": {"within": 0.75},
    }
    for doc_type, threshold in thresholds.items():
        counts = attribution_counts_by_doc_type.get(doc_type, {})
        total = int(counts.get("total", 0))
        if total <= 0:
            continue
        within = int(counts.get("within_chunk", 0))
        from_start = int(counts.get("from_start", 0))
        within_rate = within / total
        from_start_rate = from_start / total
        if within_rate < threshold["within"]:
            failures.append(
                f"Attribution threshold failed for doc_type={doc_type}: "
                f"chunk_scoped_field_rate={within_rate:.6f} < {threshold['within']:.2f}. "
                f"See debug artifacts under {output_dir}."
            )
        if "from_start" in threshold and from_start_rate < threshold["from_start"]:
            failures.append(
                f"Attribution threshold failed for doc_type={doc_type}: "
                f"chunk_scoped_field_from_start_rate={from_start_rate:.6f} < {threshold['from_start']:.2f}. "
                f"See debug artifacts under {output_dir}."
            )
    return failures


def run_on_pdfs(
    pdf_paths: List[Path],
    mode: str,
    ocr_provider: str,
    output_dir: Path,
    debug_doc: str | None = None,
):
    """
    Run harness on a list of PDFs.
    mode: "current" or "legacy_page1"
    """
    summary = {
        "mode": mode,
        "total_docs": 0,
        "multi_docs": 0,
        "template_docs": 0,
        "ifi_typed_form_docs": 0,
        "chunks_total": 0,
        "ocr_low_confidence_docs": 0,
        "template_blocked_low_conf_count": 0,
        "total_ocr_pages": 0,
        "avg_pages_per_doc": 0,
        "reason_code_counts": {},
        "false_empty_essay_count": 0,
        "docs_reviewed_count": 0,
        "needs_review_rate": 0,
        "auto_approved_count": 0,
        "auto_approve_rate": 0,
        "ocr_low_confidence_rate": 0,
        "ocr_confidence_avg": 0,
        "docs_with_any_text_count": 0,
        "docs_with_any_text_rate": 0,
        "docs_with_grade_found_count": 0,
        "docs_with_grade_found_rate": 0,
        "docs_with_school_found_count": 0,
        "docs_with_school_found_rate": 0,
        "multi_expected_docs": 0,
        "multi_detected_docs": 0,
        "multi_detection_rate": 0,
        "chunk_scoped_fields_total": 0,
        "chunk_scoped_fields_within_chunk": 0,
        "chunk_scoped_fields_from_start_page": 0,
        "chunk_scoped_field_rate": 0,
        "chunk_scoped_field_from_start_rate": 0,
        "estimated_cost_proxy": 0,
        "review_rate_by_doc_type": {},
        "doc_type_distribution": {},
        "container_docs_count": 0,
        "skipped_container_docs": 0,
    }
    failures: List[str] = []
    attribution_counts_by_doc_type: dict[str, dict[str, int]] = {}
    ocr_conf_values: list[float] = []

    docs_dir = output_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    for pdf_path in pdf_paths:
        submission_id = compute_submission_id(pdf_path)
        doc_out_dir = docs_dir / submission_id
        doc_out_dir.mkdir(parents=True, exist_ok=True)

        analysis = analyze_document(str(pdf_path), ocr_provider_name=ocr_provider)
        if debug_doc and debug_doc.lower() in pdf_path.name.lower():
            print(f"[debug-doc] {pdf_path.name}")
            print(f"  structure={analysis.structure}")
            print(f"  start_page_indices={analysis.start_page_indices}")
            print(
                "  chunk_ranges="
                + str([{"start_page": c.start_page, "end_page": c.end_page} for c in analysis.chunk_ranges])
            )

        multi_peaks = analysis.page_count >= 6 and has_multiple_header_peaks(analysis)
        if multi_peaks:
            summary["multi_expected_docs"] += 1
            if analysis.structure == "multi":
                summary["multi_detected_docs"] += 1
            else:
                failures.append(
                    f"Expected multi structure from header peaks but got {analysis.structure} for {pdf_path.name}"
                )

        if mode == "legacy_page1":
            # Force single chunk on first page only
            analysis.structure = "single"
            analysis.chunk_ranges = [ChunkRange(start_page=0, end_page=0)]
        else:
            if analysis.structure == "multi":
                summary["multi_docs"] += 1
            if analysis.structure == "template":
                summary["template_docs"] += 1
        if getattr(analysis, "form_layout", "") == "ifi_official_typed":
            summary["ifi_typed_form_docs"] += 1
        if analysis.low_confidence_for_template:
            summary["template_blocked_low_conf_count"] += 1

        doc_reason_codes: set[str] = set()
        doc_ocr_conf: list[dict] = []
        chunk_count = 0
        doc_ocr_pages = 0
        chunk_diagnostics: list[dict] = []
        doc_attr_telemetry_chunks: list[dict] = []
        doc_attr_mismatch_count = 0
        doc_attr_missing_count = 0
        doc_attr_counts = {"total": 0, "within_chunk": 0, "from_start": 0}

        doc_pages_for_ocr = [0] if mode == "legacy_page1" else None
        # Typed form submissions (native_text): use text layer only, no OCR
        if analysis.format == "native_text":
            per_page_stats, doc_ocr_pages = extract_pdf_text_layer(
                str(pdf_path),
                pages=doc_pages_for_ocr,
                mode="full",
                include_text=True,
            )
        else:
            per_page_stats, doc_ocr_pages = ocr_pdf_pages(
                str(pdf_path),
                pages=doc_pages_for_ocr,
                mode="full",
                provider_name=ocr_provider,
                include_text=True,
            )
        expected_ocr_pages = 1 if mode == "legacy_page1" else analysis.page_count
        if doc_ocr_pages != expected_ocr_pages:
            failures.append(
                f"OCR pages mismatch for {pdf_path.name}: expected={expected_ocr_pages} actual={doc_ocr_pages}"
            )
        page_indices = [int(s.get("page_index", -1)) for s in per_page_stats]
        expected_indices = list(range(expected_ocr_pages))
        if sorted(page_indices) != expected_indices:
            failures.append(
                f"OCR page indices mismatch for {pdf_path.name}: expected={expected_indices} actual={sorted(page_indices)}"
            )

        per_page_stats_sorted = sorted(per_page_stats, key=lambda x: int(x.get("page_index", 0)))
        final_text = "\n\n".join((s.get("text") or "").strip() for s in per_page_stats_sorted if (s.get("text") or "").strip())
        doc_ocr_conf = [
            {
                "page_index": int(stat.get("page_index", -1)),
                "confidence_avg": stat.get("confidence_avg"),
                "confidence_min": stat.get("confidence_min"),
                "confidence_p10": stat.get("confidence_p10"),
                "low_conf_page_count": stat.get("low_conf_page_count"),
                "char_count": stat.get("char_count"),
            }
            for stat in per_page_stats_sorted
        ]
        for stat in doc_ocr_conf:
            conf = stat.get("confidence_avg")
            if conf is not None:
                try:
                    ocr_conf_values.append(float(conf))
                except (TypeError, ValueError):
                    pass
        if final_text.strip():
            summary["docs_with_any_text_count"] += 1

        # Prepare document
        doc = fitz.open(pdf_path)
        for idx, chunk in enumerate(analysis.chunk_ranges):
            if mode == "legacy_page1":
                from_page = 0
                to_page = 0
            else:
                from_page = chunk.start_page
                to_page = chunk.end_page
            chunk_doc = fitz.open()
            chunk_doc.insert_pdf(doc, from_page=from_page, to_page=to_page, widgets=0)
            tmp_chunk = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            chunk_doc.save(tmp_chunk.name)
            chunk_doc.close()

            # Single-chunk: use original PDF so AcroForm widgets (Student's Name, School, Grade) are present
            chunk_count_total = len(analysis.chunk_ranges)
            pipeline_input_path = pdf_path if chunk_count_total == 1 else Path(tmp_chunk.name)

            rec, rep = run_chunk_pipeline(
                idx,
                pipeline_input_path,
                submission_id,
                pdf_path.name,
                analysis.format,
                analysis.structure == "template",
                ocr_provider,
                chunk_page_start=from_page,
                chunk_page_end=to_page,
                template_blocked_low_conf=analysis.low_confidence_for_template,
                doc_class=analysis.doc_class,
                analysis_structure=(
                    "single"
                    if (analysis.doc_class.value if hasattr(analysis.doc_class, "value") else str(analysis.doc_class))
                    == "BULK_SCANNED_BATCH"
                    else analysis.structure
                ),
                analysis_form_layout=analysis.form_layout,
                analysis_header_signature_score_max=max(
                    (p.header_signature_score for p in analysis.pages), default=0.0
                ),
            )
            chunk_count += 1
            chunk_codes = _normalize_reason_codes(rec.review_reason_codes)
            validation_stage = rep.get("stages", {}).get("validation", {})
            chunk_doc_type = validation_stage.get("doc_type", "UNKNOWN")
            rep_extracted = rep.get("extracted_fields", {})
            attr_pages = load_per_page_text(rep, artifact_dir="")
            if not attr_pages:
                attr_pages = per_page_stats_sorted
            rep_source_pages = compute_field_source_pages(
                per_page_text=attr_pages,
                extracted_fields=rep_extracted,
                chunk_page_start=from_page,
                chunk_page_end=to_page,
            )
            rep_attr_confidence = compute_field_attribution_confidence(
                per_page_text=attr_pages,
                extracted_fields=rep_extracted,
                chunk_page_start=from_page,
                chunk_page_end=to_page,
            )
            for field in ("student_name", "school_name", "grade"):
                if rep_extracted.get(field) is not None:
                    summary["chunk_scoped_fields_total"] += 1
                    source_page = rep_source_pages.get(field)
                    if (
                        source_page is not None
                        and from_page <= source_page <= to_page
                    ):
                        summary["chunk_scoped_fields_within_chunk"] += 1
                    if source_page == from_page:
                        summary["chunk_scoped_fields_from_start_page"] += 1
                    doc_attr_counts["total"] += 1
                    if source_page is not None and from_page <= source_page <= to_page:
                        doc_attr_counts["within_chunk"] += 1
                    if source_page == from_page:
                        doc_attr_counts["from_start"] += 1

            chunk_telemetry = assert_expected_attribution(
                chunk_doc_type,
                {"chunk_page_start": from_page, "chunk_page_end": to_page},
                rep_extracted,
                rep_source_pages,
            )
            doc_attr_mismatch_count += len(chunk_telemetry["attribution_mismatches"])
            doc_attr_missing_count += len(chunk_telemetry["attribution_missing"])
            doc_attr_telemetry_chunks.append(
                {
                    "chunk_index": idx,
                    "chunk_submission_id": rec.submission_id,
                    "doc_type": chunk_doc_type,
                    **chunk_telemetry,
                }
            )

            chunk_artifact_dir = doc_out_dir / rec.submission_id
            chunk_artifact_dir.mkdir(parents=True, exist_ok=True)
            with open(chunk_artifact_dir / "field_source_pages.json", "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "chunk_submission_id": rec.submission_id,
                        "chunk_page_start": from_page,
                        "chunk_page_end": to_page,
                        "field_source_pages": rep_source_pages,
                    },
                    f,
                    indent=2,
                )
            write_field_attribution_debug_artifact(
                chunk_artifact_dir=chunk_artifact_dir,
                submission_id=submission_id,
                chunk_submission_id=rec.submission_id,
                doc_type=chunk_doc_type,
                chunk_page_start=from_page,
                chunk_page_end=to_page,
                extracted_fields=rep_extracted,
                field_source_pages=rep_source_pages,
                per_page_text=attr_pages,
            )
            chunk_diagnostics.append(
                {
                    "chunk_index": idx,
                    "chunk_page_start": from_page,
                    "chunk_page_end": to_page,
                    "chunk_submission_id": rec.submission_id,
                    "doc_class": rec.doc_class.value if hasattr(rec.doc_class, "value") else str(rec.doc_class),
                    "doc_type": chunk_doc_type,
                    "doc_role": validation_stage.get("doc_role", "document"),
                    "chunk_reason_codes": chunk_codes,
                    "chunk_needs_review": rec.needs_review,
                    "extracted_fields": rep_extracted,
                    "field_source_pages": rep_source_pages,
                    "field_attribution_confidence": rep_attr_confidence,
                    "grade_normalization": validation_stage.get("grade_normalization"),
                    "school_reference_validation": validation_stage.get("school_reference_validation"),
                }
            )
            if rec.needs_review and not chunk_codes:
                failures.append(
                    f"Invariant violated: chunk needs_review=True with empty reason codes ({pdf_path.name} chunk {idx})."
                )
            if debug_doc and debug_doc.lower() in pdf_path.name.lower():
                print(
                    f"  chunk[{idx}] start_page={from_page} "
                    f"student={rep_extracted.get('student_name')!r}@{rep_source_pages.get('student_name')} "
                    f"grade={rep_extracted.get('grade')!r}@{rep_source_pages.get('grade')} "
                    f"school={rep_extracted.get('school_name')!r}@{rep_source_pages.get('school_name')}"
                )
            try:
                Path(tmp_chunk.name).unlink()
            except Exception:
                pass
        doc.close()

        extracted = extract_doc_fields_from_final_text(final_text)
        doc_type = route_doc_type(
            analysis,
            final_text,
            has_acroform=detect_pdf_has_acroform_fields(str(pdf_path)),
        )
        doc_role = classify_doc_role(
            {
                "doc_type": doc_type,
                "doc_class": analysis.doc_class,
                "analysis_structure": analysis.structure,
                "chunk_index": None,
            },
            {"analysis": {"structure": analysis.structure}},
            chunk_metadata=None,
        )
        summary["doc_type_distribution"][doc_type] = summary["doc_type_distribution"].get(doc_type, 0) + 1
        type_counts = attribution_counts_by_doc_type.setdefault(
            doc_type, {"total": 0, "within_chunk": 0, "from_start": 0}
        )
        type_counts["total"] += doc_attr_counts["total"]
        type_counts["within_chunk"] += doc_attr_counts["within_chunk"]
        type_counts["from_start"] += doc_attr_counts["from_start"]
        # Merge pipeline chunk results so missing-metadata flags use pipeline findings
        for diag in chunk_diagnostics:
            ef = diag.get("extracted_fields") or {}
            for field in ("student_name", "school_name", "grade"):
                val = ef.get(field)
                if val and not extracted.get(field):
                    if field == "school_name" and looks_like_essay_fragment(val):
                        continue  # Don't use essay text as school name
                    extracted[field] = val
        if extracted.get("grade"):
            summary["docs_with_grade_found_count"] += 1
        if extracted.get("school_name"):
            summary["docs_with_school_found_count"] += 1

        _, missing_field_evidence = compute_doc_reason_codes(
            extracted=extracted,
            final_text=final_text,
            submission_id=submission_id,
            is_template_doc=(analysis.structure == "template"),
            template_blocked_low_conf=analysis.low_confidence_for_template,
        )
        # Parent status must derive from children (logical OR) to prevent silent success masking child failures.
        doc_needs_review, doc_reason_codes = aggregate_parent_status_from_children(chunk_diagnostics)
        is_container_parent = doc_role == DocRole.CONTAINER
        if doc_needs_review and not doc_reason_codes:
            failures.append(f"Invariant violated: needs_review=True with empty reason codes ({pdf_path.name})")

        summary["chunks_total"] += chunk_count
        summary["total_ocr_pages"] += doc_ocr_pages if doc_ocr_pages > 0 else expected_ocr_pages
        apply_doc_review_metrics(
            summary,
            doc_role=doc_role,
            doc_type=doc_type,
            doc_needs_review=doc_needs_review,
            doc_reason_codes=doc_reason_codes,
            failures=failures,
            pdf_name=pdf_path.name,
        )

        # doc summary
        # Special assertion for Valeria-Pantoja to ensure multi detection with full OCR
        if pdf_path.name.lower().startswith("valeria-pantoja") and mode == "current":
            if analysis.structure != "multi" or chunk_count <= 1:
                failures.append("Valeria-Pantoja expected multi structure in current mode.")
        doc_summary = {
            "submission_id": submission_id,
            "filename": pdf_path.name,
            "page_count": analysis.page_count,
            "format": analysis.format,
            "structure": analysis.structure,
            "form_layout": getattr(analysis, "form_layout", "unknown"),
            "doc_class": analysis.doc_class.value if hasattr(analysis.doc_class, "value") else str(analysis.doc_class),
            "chunk_count": chunk_count,
            "needs_review": doc_needs_review,
            "reason_codes": sorted(list(doc_reason_codes)),
            "doc_type": doc_type,
            "doc_role": doc_role.value,
            "extracted": extracted,
            "missing_field_evidence": missing_field_evidence,
            "chunk_diagnostics": chunk_diagnostics,
            "attribution_telemetry": {
                "chunks": doc_attr_telemetry_chunks,
            },
            "attribution_mismatch_count": doc_attr_mismatch_count,
            "attribution_missing_count": doc_attr_missing_count,
            "ocr_conf_stats": doc_ocr_conf,
            "total_ocr_pages": doc_ocr_pages if doc_ocr_pages > 0 else expected_ocr_pages,
            "final_text_char_count": len(final_text),
        }
        with open(doc_out_dir / "doc_summary.json", "w", encoding="utf-8") as f:
            json.dump(doc_summary, f, indent=2)

    # Rates and derived metrics
    effective_docs = summary["total_docs"]
    if summary["total_docs"] > 0:
        summary["avg_pages_per_doc"] = summary["total_ocr_pages"] / summary["total_docs"]
        if effective_docs > 0:
            summary["needs_review_rate"] = summary["docs_reviewed_count"] / effective_docs
            summary["auto_approve_rate"] = summary["auto_approved_count"] / effective_docs
        else:
            summary["needs_review_rate"] = 0
            summary["auto_approve_rate"] = 0
        summary["ocr_low_confidence_rate"] = summary["ocr_low_confidence_docs"] / summary["total_docs"]
        summary["docs_with_any_text_rate"] = summary["docs_with_any_text_count"] / summary["total_docs"]
        summary["docs_with_grade_found_rate"] = summary["docs_with_grade_found_count"] / summary["total_docs"]
        summary["docs_with_school_found_rate"] = summary["docs_with_school_found_count"] / summary["total_docs"]
        if summary["multi_expected_docs"] > 0:
            summary["multi_detection_rate"] = summary["multi_detected_docs"] / summary["multi_expected_docs"]
        if summary["chunk_scoped_fields_total"] > 0:
            summary["chunk_scoped_field_rate"] = (
                summary["chunk_scoped_fields_within_chunk"] / summary["chunk_scoped_fields_total"]
            )
            summary["chunk_scoped_field_from_start_rate"] = (
                summary["chunk_scoped_fields_from_start_page"] / summary["chunk_scoped_fields_total"]
            )
    summary["estimated_cost_proxy"] = summary["total_ocr_pages"]
    if ocr_conf_values:
        summary["ocr_confidence_avg"] = sum(ocr_conf_values) / len(ocr_conf_values)
    for doc_type, bucket in summary["review_rate_by_doc_type"].items():
        total = bucket.get("total", 0)
        bucket["review_rate"] = (bucket.get("needs_review", 0) / total) if total else 0

    for code, count in summary["reason_code_counts"].items():
        if count > summary["total_docs"]:
            failures.append(
                f"Doc-level reason count exceeds total_docs for {code}: count={count} total_docs={summary['total_docs']}"
            )
        if code == "PENDING_REVIEW":
            failures.append("Forbidden reason code PENDING_REVIEW present in reason_code_counts.")

    failures.extend(enforce_attribution_thresholds(attribution_counts_by_doc_type, output_dir))
    return summary, failures


def compare_summaries(current: dict, legacy: dict, docs_current: Path, docs_legacy: Path, output_path: Path):
    """Create before/after comparison report using batch and per-doc summaries."""
    def delta(a, b):
        return a - b

    reason_codes = set(current.get("reason_code_counts", {}).keys()) | set(legacy.get("reason_code_counts", {}).keys())
    reason_delta = {}
    for code in sorted(reason_codes):
        reason_delta[code] = {
            "current": current.get("reason_code_counts", {}).get(code, 0),
            "legacy": legacy.get("reason_code_counts", {}).get(code, 0),
            "delta": current.get("reason_code_counts", {}).get(code, 0) - legacy.get("reason_code_counts", {}).get(code, 0),
        }

    # Most improved docs: EMPTY_ESSAY in legacy but not in current
    improved = []
    if docs_current.exists() and docs_legacy.exists():
        for legacy_doc in docs_legacy.glob("*/doc_summary.json"):
            with open(legacy_doc, "r", encoding="utf-8") as f:
                ldoc = json.load(f)
            if "EMPTY_ESSAY" not in ldoc.get("reason_codes", []):
                continue
            sid = legacy_doc.parent.name
            current_doc_path = docs_current / sid / "doc_summary.json"
            if current_doc_path.exists():
                with open(current_doc_path, "r", encoding="utf-8") as f:
                    cdoc = json.load(f)
                if "EMPTY_ESSAY" not in cdoc.get("reason_codes", []):
                    improved.append({"submission_id": sid, "filename": cdoc.get("filename"), "legacy_reason_codes": ldoc.get("reason_codes"), "current_reason_codes": cdoc.get("reason_codes")})
    improved = improved[:10]

    # Cost drivers: top 10 docs by total_ocr_pages in current
    cost_drivers = []
    if docs_current.exists():
        docs_list = []
        for doc_path in docs_current.glob("*/doc_summary.json"):
            with open(doc_path, "r", encoding="utf-8") as f:
                doc = json.load(f)
            docs_list.append({"submission_id": doc_path.parent.name, "filename": doc.get("filename"), "total_ocr_pages": doc.get("total_ocr_pages", 0)})
        docs_list.sort(key=lambda x: x["total_ocr_pages"], reverse=True)
        cost_drivers = docs_list[:10]

    report = {
        "false_empty_essay_delta": delta(current.get("false_empty_essay_count", 0), legacy.get("false_empty_essay_count", 0)),
        "multi_docs_detected_delta": delta(current.get("multi_docs", 0), legacy.get("multi_docs", 0)),
        "template_docs_delta": delta(current.get("template_docs", 0), legacy.get("template_docs", 0)),
        "needs_review_rate_delta": delta(current.get("needs_review_rate", 0), legacy.get("needs_review_rate", 0)),
        "ocr_low_confidence_rate_delta": delta(current.get("ocr_low_confidence_rate", 0), legacy.get("ocr_low_confidence_rate", 0)),
        "total_ocr_pages_delta": delta(current.get("total_ocr_pages", 0), legacy.get("total_ocr_pages", 0)),
        "avg_pages_per_doc_delta": delta(current.get("avg_pages_per_doc", 0), legacy.get("avg_pages_per_doc", 0)),
        "reason_code_counts": reason_delta,
        "most_improved_docs": improved,
        "cost_drivers": cost_drivers,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO_ROOT / ".env")
        # Allow override from cwd .env or shell (e.g. export GROQ_API_KEY=valid_key)
        load_dotenv(Path.cwd() / ".env")
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Run regression checks for document analysis.")
    parser.add_argument("--ocr-provider", default="stub", help="OCR provider to use (default: stub)")
    parser.add_argument("--pdf-dir", type=Path, help="Directory of PDFs to run harness on")
    parser.add_argument("--pdf-glob", default="*.pdf", help="Glob pattern for PDFs")
    parser.add_argument("--max-docs", type=int, default=None, help="Maximum number of PDFs to process")
    parser.add_argument("--output-dir", type=Path, help="Output directory for harness artifacts")
    parser.add_argument("--debug-doc", help="Print detailed chunk extraction debug for matching filename")
    parser.add_argument("--simulate-legacy-page1", action="store_true", help="Also run legacy page-1-only mode and compare")
    parser.add_argument("--compare-to", type=Path, help="Optional baseline run_snapshot.json for drift comparison")
    args = parser.parse_args()

    tmpdir = Path(tempfile.mkdtemp(prefix="regression_checks_"))

    # If user provides pdf-dir, run real harness paths
    if args.pdf_dir:
        pdf_paths = sorted(args.pdf_dir.glob(args.pdf_glob))
        if args.max_docs:
            pdf_paths = pdf_paths[: args.max_docs]
        if not pdf_paths:
            print("No PDFs found for provided directory/glob.")
            return 1
        out_base = args.output_dir or (REPO_ROOT / "artifacts" / "harness_runs" / time.strftime("%Y%m%d_%H%M%S"))
        out_base.mkdir(parents=True, exist_ok=True)

        # Current mode
        current_dir = out_base / "current"
        current_dir.mkdir(parents=True, exist_ok=True)
        current_summary, failures_current = run_on_pdfs(
            pdf_paths, "current", args.ocr_provider, current_dir, debug_doc=args.debug_doc
        )
        with open(current_dir / "batch_summary.current.json", "w", encoding="utf-8") as f:
            json.dump(current_summary, f, indent=2)
        current_snapshot = build_run_snapshot(current_summary)
        with open(current_dir / "run_snapshot.json", "w", encoding="utf-8") as f:
            json.dump(current_snapshot, f, indent=2)

        all_failures = list(failures_current)
        if args.compare_to:
            with open(args.compare_to, "r", encoding="utf-8") as f:
                baseline_snapshot = json.load(f)
            ok, drift_report = compare_snapshots(current_snapshot, baseline_snapshot)
            with open(out_base / "drift_report.json", "w", encoding="utf-8") as f:
                json.dump(drift_report, f, indent=2)
            if not ok:
                all_failures.extend(drift_report.get("issues", []))
        # Typed-form tc01–tc08: missing fields must be flagged for review, never fail; record always produced.
        all_failures.extend(
            validate_typed_form_missing_field_expectations(pdf_paths, current_dir / "docs")
        )

        if args.simulate_legacy_page1:
            legacy_dir = out_base / "legacy"
            legacy_dir.mkdir(parents=True, exist_ok=True)
            legacy_summary, failures_legacy = run_on_pdfs(
                pdf_paths, "legacy_page1", args.ocr_provider, legacy_dir, debug_doc=args.debug_doc
            )
            with open(legacy_dir / "batch_summary.legacy.json", "w", encoding="utf-8") as f:
                json.dump(legacy_summary, f, indent=2)
            all_failures.extend(failures_legacy)

            compare_summaries(
                current_summary,
                legacy_summary,
                docs_current=current_dir / "docs",
                docs_legacy=legacy_dir / "docs",
                output_path=out_base / "before_after_summary.json",
            )

        if all_failures:
            print("FAILURES:")
            for fmsg in all_failures:
                print(f" - {fmsg}")
            return 1
        print(f"Summary written to {out_base}")
        return 0

    # Default synthetic fixtures mode (no pdf-dir)
    fixtures = {
        "multi": generate_multi_fixture(tmpdir),
        "template": REPO_ROOT / "docs" / "22-IFI-Essay-Form-34.pdf",
        "scanned": generate_scanned_fixture(tmpdir),
    }
    if not fixtures["template"].exists():
        print("Template fixture docs/22-IFI-Essay-Form-34.pdf is missing.")
        return 1

    hybrid_path = generate_hybrid_fixture(tmpdir)
    low_conf_template_path = generate_scanned_fixture(tmpdir)  # reuse blank image-only; will be OCR'd by low-conf provider

    failures: List[str] = []
    summary = {
        "total_docs": 4,
        "multi_docs": 0,
        "template_docs": 0,
        "chunks_total": 0,
        "ocr_low_confidence_docs": 0,
        "template_blocked_low_conf_count": 0,
        "total_ocr_pages": 0,
        "avg_pages_per_doc": 0,
        "reason_code_counts": {},
        "false_empty_essay_count": 0,
    }

    # TEST 1: Multi-submission bundle
    multi_analysis = analyze_document(str(fixtures["multi"]), ocr_provider_name=args.ocr_provider)
    summary["total_ocr_pages"] += multi_analysis.page_count
    if multi_analysis.structure != "multi" or len(multi_analysis.chunk_ranges) <= 1:
        failures.append("Multi bundle not detected as multi.")
    else:
        summary["multi_docs"] += 1
    # coverage check
    if multi_analysis.chunk_ranges:
        covered = []
        for c in multi_analysis.chunk_ranges:
            covered.extend(list(range(c.start_page, c.end_page + 1)))
        if sorted(covered) != list(range(multi_analysis.page_count)):
            failures.append("Multi chunk ranges do not cover all pages.")

    # Process multi chunks
    for idx, path in chunk_paths(fixtures["multi"], multi_analysis.chunk_ranges, tmpdir):
        rec, _ = run_chunk_pipeline(
            idx,
            path,
            "multi_parent",
            fixtures["multi"].name,
            multi_analysis.format,
            False,
            args.ocr_provider,
            doc_class=multi_analysis.doc_class,
            analysis_structure=multi_analysis.structure,
            analysis_form_layout=multi_analysis.form_layout,
            analysis_header_signature_score_max=max(
                (p.header_signature_score for p in multi_analysis.pages), default=0.0
            ),
        )
        summary["chunks_total"] += 1
        if "EMPTY_ESSAY" in rec.review_reason_codes:
            summary["false_empty_essay_count"] += 1
        for code in _normalize_reason_codes(rec.review_reason_codes):
            summary["reason_code_counts"][code] = summary["reason_code_counts"].get(code, 0) + 1
            if "=" in code or code not in ALLOWED_REASON_CODES:
                failures.append(f"Reason code not enum: {code}")

    # TEST 2: Template-only
    template_analysis = analyze_document(str(fixtures["template"]), ocr_provider_name=args.ocr_provider)
    summary["total_ocr_pages"] += template_analysis.page_count
    if template_analysis.structure == "template":
        summary["template_docs"] += 1
    else:
        failures.append("Template form not classified as template.")
    rec, _ = run_chunk_pipeline(
        0,
        fixtures["template"],
        "template_parent",
        fixtures["template"].name,
        template_analysis.format,
        template_analysis.structure == "template",
        args.ocr_provider,
        doc_class=template_analysis.doc_class,
        analysis_structure=template_analysis.structure,
        analysis_form_layout=template_analysis.form_layout,
        analysis_header_signature_score_max=max(
            (p.header_signature_score for p in template_analysis.pages), default=0.0
        ),
    )
    if "TEMPLATE_ONLY" not in rec.review_reason_codes:
        failures.append("Template record missing TEMPLATE_ONLY code.")
    for code in _normalize_reason_codes(rec.review_reason_codes):
        summary["reason_code_counts"][code] = summary["reason_code_counts"].get(code, 0) + 1
        if "=" in code or code not in ALLOWED_REASON_CODES:
            failures.append(f"Reason code not enum: {code}")
    if template_analysis.low_confidence_for_template:
        summary["template_blocked_low_conf_count"] += 1

    # TEST 3: Scanned handwriting
    scanned_analysis = analyze_document(str(fixtures["scanned"]), ocr_provider_name=args.ocr_provider)
    summary["total_ocr_pages"] += scanned_analysis.page_count
    if scanned_analysis.format != "image_only":
        failures.append("Scanned handwriting not classified image_only.")
    rec, report = run_chunk_pipeline(
        0,
        fixtures["scanned"],
        "scanned_parent",
        fixtures["scanned"].name,
        scanned_analysis.format,
        False,
        args.ocr_provider,
        doc_class=scanned_analysis.doc_class,
        analysis_structure=scanned_analysis.structure,
        analysis_form_layout=scanned_analysis.form_layout,
        analysis_header_signature_score_max=max(
            (p.header_signature_score for p in scanned_analysis.pages), default=0.0
        ),
    )
    ocr_summary = report.get("ocr_summary", {})
    if ocr_summary.get("confidence_min") is None or ocr_summary.get("confidence_p10") is None:
        failures.append("OCR confidence stats missing for scanned doc.")
    if "OCR_LOW_CONFIDENCE" in rec.review_reason_codes:
        summary["ocr_low_confidence_docs"] += 1
    for code in _normalize_reason_codes(rec.review_reason_codes):
        summary["reason_code_counts"][code] = summary["reason_code_counts"].get(code, 0) + 1
        if "=" in code or code not in ALLOWED_REASON_CODES:
            failures.append(f"Reason code not enum: {code}")

    # TEST 4: Hybrid synthetic
    hybrid_analysis = analyze_document(str(hybrid_path), ocr_provider_name=args.ocr_provider)
    summary["total_ocr_pages"] += hybrid_analysis.page_count
    if hybrid_analysis.format != "hybrid":
        failures.append("Hybrid synthetic not classified hybrid.")
    rec, _ = run_chunk_pipeline(
        0,
        hybrid_path,
        "hybrid_parent",
        hybrid_path.name,
        hybrid_analysis.format,
        False,
        args.ocr_provider,
        doc_class=hybrid_analysis.doc_class,
        analysis_structure=hybrid_analysis.structure,
        analysis_form_layout=hybrid_analysis.form_layout,
        analysis_header_signature_score_max=max(
            (p.header_signature_score for p in hybrid_analysis.pages), default=0.0
        ),
    )
    if rec.word_count == 0:
        failures.append("Hybrid chunk produced EMPTY_ESSAY.")
    for code in _normalize_reason_codes(rec.review_reason_codes):
        summary["reason_code_counts"][code] = summary["reason_code_counts"].get(code, 0) + 1
        if "=" in code or code not in ALLOWED_REASON_CODES:
            failures.append(f"Reason code not enum: {code}")

    # TEST 5: Template blocked by low OCR confidence (forced low-conf provider)
    import pipeline.ocr as ocr_module
    import pipeline.document_analysis as da_module
    original_get_provider = ocr_module.get_ocr_provider
    da_original_get = da_module.get_ocr_provider
    try:
        ocr_module.get_ocr_provider = lambda name="stub": LowConfProvider()
        da_module.get_ocr_provider = lambda name="stub": LowConfProvider()
        low_conf_analysis = analyze_document(str(low_conf_template_path), ocr_provider_name="stub")
        summary["total_ocr_pages"] += low_conf_analysis.page_count
        if low_conf_analysis.structure == "template":
            failures.append("Low-confidence template classified as template.")
        if not low_conf_analysis.low_confidence_for_template:
            failures.append("low_confidence_for_template flag not set.")
        rec, _ = run_chunk_pipeline(
            0,
            low_conf_template_path,
            "lowconf_parent",
            low_conf_template_path.name,
            low_conf_analysis.format,
            low_conf_analysis.structure == "template",
            "stub",
            template_blocked_low_conf=low_conf_analysis.low_confidence_for_template,
            doc_class=low_conf_analysis.doc_class,
            analysis_structure=low_conf_analysis.structure,
            analysis_form_layout=low_conf_analysis.form_layout,
            analysis_header_signature_score_max=max(
                (p.header_signature_score for p in low_conf_analysis.pages), default=0.0
            ),
        )
        if "OCR_LOW_CONFIDENCE" not in rec.review_reason_codes:
            failures.append("Low-confidence template missing OCR_LOW_CONFIDENCE code.")
        else:
            summary["ocr_low_confidence_docs"] += 1
            summary["template_blocked_low_conf_count"] += 1
        for code in _normalize_reason_codes(rec.review_reason_codes):
            summary["reason_code_counts"][code] = summary["reason_code_counts"].get(code, 0) + 1
            if "=" in code or code not in ALLOWED_REASON_CODES:
                failures.append(f"Reason code not enum: {code}")
    finally:
        ocr_module.get_ocr_provider = original_get_provider
        da_module.get_ocr_provider = da_original_get

    # Write summary artifact
    if summary["total_docs"] > 0:
        summary["avg_pages_per_doc"] = summary["total_ocr_pages"] / summary["total_docs"]

    summary_path = tmpdir / "batch_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Summary written to {summary_path}")
    if failures:
        print("FAILURES:")
        for fmsg in failures:
            print(f" - {fmsg}")
        return 1
    print("All regression checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
