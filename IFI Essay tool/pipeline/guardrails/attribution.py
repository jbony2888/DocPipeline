from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

REQUIRED_HEADER_FIELDS = ("student_name", "school_name", "grade")


def normalize_text(s: str) -> str:
    if s is None:
        return ""
    text = str(s).casefold()
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _coerce_page_entries(raw_pages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in raw_pages or []:
        try:
            page_index = int(entry.get("page_index"))
        except Exception:
            continue
        text = entry.get("text") or ""
        out.append({"page_index": page_index, "text": str(text)})
    out.sort(key=lambda p: p["page_index"])
    return out


def _best_fuzzy_ratio(needle_norm: str, haystack_text: str) -> float:
    if not needle_norm:
        return 0.0
    best = 0.0
    lines = (haystack_text or "").splitlines() or [haystack_text or ""]
    for line in lines:
        ratio = SequenceMatcher(None, needle_norm, normalize_text(line)).ratio()
        if ratio > best:
            best = ratio
    return best


def _ratio_to_confidence(ratio: float) -> float | None:
    if ratio >= 0.92:
        scaled = 0.85 + ((ratio - 0.92) / 0.08) * 0.10
        return round(min(0.95, max(0.85, scaled)), 6)
    if 0.85 <= ratio < 0.92:
        scaled = 0.70 + ((ratio - 0.85) / 0.07) * 0.15
        return round(min(0.85, max(0.70, scaled)), 6)
    return None


def find_value_attribution(
    per_page_text: list[dict], value: str, start: int, end: int
) -> dict | None:
    raw_value = str(value or "")
    needle_norm = normalize_text(raw_value)
    if not needle_norm:
        return None
    for page in sorted(per_page_text or [], key=lambda p: int(p.get("page_index", 0))):
        page_index = int(page.get("page_index", -1))
        if page_index < start or page_index > end:
            continue
        page_text = str(page.get("text") or "")
        if raw_value and raw_value in page_text:
            return {"page_index": page_index, "confidence": 1.0, "method": "exact_match"}
        normalized_page = normalize_text(page_text)
        if needle_norm in normalized_page:
            return {
                "page_index": page_index,
                "confidence": 0.9,
                "method": "normalized_contains",
            }
        ratio = _best_fuzzy_ratio(needle_norm, page_text)
        conf = _ratio_to_confidence(ratio)
        if conf is not None:
            return {"page_index": page_index, "confidence": conf, "method": "fuzzy_match"}
    return None


def _normalize_grade_digits(grade: int | str | None) -> str | None:
    if grade is None:
        return None
    if isinstance(grade, int):
        return str(grade)
    grade_str = str(grade).strip()
    if not grade_str:
        return None
    if grade_str.isdigit():
        return grade_str
    match = re.search(r"\b(\d{1,2})\b", grade_str)
    if match:
        return match.group(1)
    return None


def find_grade_attribution(
    per_page_text: list[dict], grade: int | str, start: int, end: int
) -> dict | None:
    grade_digits = _normalize_grade_digits(grade)
    if not grade_digits:
        return None
    grade_pattern = re.compile(rf"\b(?:grade|grado)\s*{re.escape(grade_digits)}\b")
    for page in sorted(per_page_text or [], key=lambda p: int(p.get("page_index", 0))):
        page_index = int(page.get("page_index", -1))
        if page_index < start or page_index > end:
            continue
        normalized_page = normalize_text(page.get("text") or "")
        if grade_pattern.search(normalized_page):
            return {
                "page_index": page_index,
                "confidence": 0.9,
                "method": "normalized_contains",
            }
    return None


def compute_field_attribution_confidence(
    per_page_text: list[dict],
    extracted_fields: dict,
    chunk_page_start: int,
    chunk_page_end: int,
) -> dict:
    result = {"student_name": None, "school_name": None, "grade": None}
    if extracted_fields is None:
        return result

    student_name = extracted_fields.get("student_name")
    school_name = extracted_fields.get("school_name")
    grade = extracted_fields.get("grade")

    if student_name is not None:
        result["student_name"] = find_value_attribution(
            per_page_text, str(student_name), chunk_page_start, chunk_page_end
        )
    if school_name is not None:
        result["school_name"] = find_value_attribution(
            per_page_text, str(school_name), chunk_page_start, chunk_page_end
        )
    if grade is not None:
        result["grade"] = find_grade_attribution(
            per_page_text, grade, chunk_page_start, chunk_page_end
        )
    return result


def compute_field_source_pages(
    per_page_text: list[dict],
    extracted_fields: dict,
    chunk_page_start: int,
    chunk_page_end: int,
) -> dict:
    detailed = compute_field_attribution_confidence(
        per_page_text, extracted_fields, chunk_page_start, chunk_page_end
    )
    return {
        field: (details or {}).get("page_index")
        for field, details in detailed.items()
    }


def load_per_page_text(report: dict, artifact_dir: str) -> list[dict]:
    ocr_summary = (report or {}).get("ocr_summary") or {}
    pages = ocr_summary.get("pages")
    if isinstance(pages, list):
        coerced = _coerce_page_entries(pages)
        if coerced:
            return coerced

    for key in ("ocr_pages", "pages"):
        candidate = (report or {}).get(key)
        if isinstance(candidate, list):
            coerced = _coerce_page_entries(candidate)
            if coerced:
                return coerced

    if artifact_dir:
        path = Path(artifact_dir) / "ocr_pages.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, list):
                    coerced = _coerce_page_entries(raw)
                    if coerced:
                        return coerced
            except Exception:
                pass
    return []


def assert_expected_attribution(
    doc_type: str,
    chunk_metadata: dict,
    extracted_fields: dict,
    field_source_pages: dict,
) -> dict:
    telemetry = {
        "attribution_expected": False,
        "attribution_mismatches": [],
        "attribution_missing": [],
    }
    if doc_type != "ifi_typed_form_submission":
        return telemetry

    expected_page = chunk_metadata.get("chunk_page_start")
    telemetry["attribution_expected"] = True
    for field in REQUIRED_HEADER_FIELDS:
        value_present = extracted_fields.get(field) is not None
        actual_page = (field_source_pages or {}).get(field)
        if value_present and actual_page is None:
            telemetry["attribution_missing"].append(
                {"field": field, "value_present": True}
            )
        elif value_present and expected_page is not None and actual_page != expected_page:
            telemetry["attribution_mismatches"].append(
                {
                    "field": field,
                    "expected_page": expected_page,
                    "actual_page": actual_page,
                }
            )
    return telemetry


def build_field_attribution_debug_payload(
    *,
    submission_id: str,
    chunk_submission_id: str,
    doc_type: str,
    chunk_page_start: int,
    chunk_page_end: int,
    extracted_fields: dict,
    field_source_pages: dict,
    per_page_text: list[dict],
    top_k: int = 3,
) -> dict | None:
    missing_fields = []
    pages_scanned = list(range(int(chunk_page_start), int(chunk_page_end) + 1))
    for field in REQUIRED_HEADER_FIELDS:
        value = (extracted_fields or {}).get(field)
        source_page = (field_source_pages or {}).get(field)
        if value is None or source_page is not None:
            continue
        normalized_value = normalize_text(str(value))
        candidates = []
        for page in sorted(per_page_text or [], key=lambda p: int(p.get("page_index", 0))):
            page_index = int(page.get("page_index", -1))
            if page_index < chunk_page_start or page_index > chunk_page_end:
                continue
            raw_text = str(page.get("text") or "")
            normalized_page = normalize_text(raw_text)
            if not normalized_value or not normalized_page:
                score = 0.0
            else:
                score = SequenceMatcher(None, normalized_value, normalized_page).ratio()
            candidates.append(
                {
                    "page_index": page_index,
                    "similarity_score": round(float(score), 6),
                    "snippet_200_chars": raw_text[:200],
                }
            )
        candidates.sort(
            key=lambda item: (-float(item["similarity_score"]), int(item["page_index"]))
        )
        missing_fields.append(
            {
                "field": field,
                "normalized_value": normalized_value,
                "pages_scanned": pages_scanned,
                "top_candidates": candidates[:top_k],
            }
        )

    if not missing_fields:
        return None

    return {
        "submission_id": submission_id,
        "chunk_submission_id": chunk_submission_id,
        "doc_type": doc_type,
        "chunk_page_start": chunk_page_start,
        "chunk_page_end": chunk_page_end,
        "extracted_fields": {
            field: (extracted_fields or {}).get(field) for field in REQUIRED_HEADER_FIELDS
        },
        "missing_fields": missing_fields,
    }

