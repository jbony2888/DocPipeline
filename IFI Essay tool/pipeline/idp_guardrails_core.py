"""
Standalone guardrails core extracted from ifi.
Copy this file into another project to reuse validation, attribution, and drift checks.
Dependency note: stdlib-only.
"""

from __future__ import annotations

import csv
import json
import os
import re
from difflib import SequenceMatcher
from enum import Enum
from pathlib import Path
from typing import Any, Dict, NamedTuple, Set, Tuple


ALLOWED_REASON_CODES = {
    "MISSING_STUDENT_NAME",
    "MISSING_GRADE",
    "MISSING_SCHOOL_NAME",
    "EMPTY_ESSAY",
    "SHORT_ESSAY",
    "OCR_LOW_CONFIDENCE",
    "EXTRACTION_FALLBACK_USED",
    "TEMPLATE_ONLY",
    "DOC_TYPE_UNKNOWN",
    "INVALID_GRADE_RANGE",
    "UNKNOWN_SCHOOL",
    "POSSIBLE_FIELD_SWAP",
}


POLICY_VERSION = "v1"


class ValidationPolicy(NamedTuple):
    required_fields: Set[str]
    min_essay_words: int
    require_essay: bool
    min_ocr_confidence: float | None
    review_on_fallback_extraction: bool


_POLICIES: Dict[str, ValidationPolicy] = {
    "ifi_typed_form_submission": ValidationPolicy(
        required_fields={"student_name", "grade", "school_name"},
        min_essay_words=50,
        require_essay=True,
        min_ocr_confidence=None,
        review_on_fallback_extraction=True,
    ),
    "ifi_official_form_scanned": ValidationPolicy(
        required_fields={"student_name", "grade", "school_name"},
        min_essay_words=50,
        require_essay=True,
        min_ocr_confidence=0.50,
        review_on_fallback_extraction=True,
    ),
    "ifi_official_form_filled": ValidationPolicy(
        required_fields={"student_name", "grade", "school_name"},
        min_essay_words=50,
        require_essay=True,
        min_ocr_confidence=None,
        review_on_fallback_extraction=True,
    ),
    "essay_with_header_metadata": ValidationPolicy(
        required_fields={"student_name", "grade", "school_name"},
        min_essay_words=50,
        require_essay=True,
        min_ocr_confidence=None,
        review_on_fallback_extraction=True,
    ),
    "standard_freeform_essay": ValidationPolicy(
        required_fields={"student_name", "grade", "school_name"},
        min_essay_words=50,
        require_essay=True,
        min_ocr_confidence=None,
        review_on_fallback_extraction=False,
    ),
    "bulk_scanned_batch": ValidationPolicy(
        required_fields={"student_name", "grade", "school_name"},
        min_essay_words=0,
        require_essay=False,
        min_ocr_confidence=None,
        review_on_fallback_extraction=False,
    ),
    "template": ValidationPolicy(
        required_fields={"student_name", "grade", "school_name"},
        min_essay_words=0,
        require_essay=False,
        min_ocr_confidence=None,
        review_on_fallback_extraction=False,
    ),
    "unknown": ValidationPolicy(
        required_fields={"student_name", "grade", "school_name"},
        min_essay_words=50,
        require_essay=True,
        min_ocr_confidence=None,
        review_on_fallback_extraction=True,
    ),
}


def _normalize_doc_type(record: dict, report: dict) -> str:
    legacy = (record.get("doc_type") or "").strip()
    if not legacy:
        ex_debug = (report or {}).get("extraction_debug") or {}
        ifi = ex_debug.get("ifi_classification") or {}
        legacy = (ifi.get("doc_type") or "").strip()
    if not legacy and record.get("template_detected"):
        return "template"
    if not legacy:
        return "unknown"

    low = legacy.lower()
    legacy_map = {
        "ifi_typed_form_submission": "ifi_typed_form_submission",
        "ifi_official_form_scanned": "ifi_official_form_scanned",
        "ifi_official_form_filled": "ifi_official_form_filled",
        "essay_with_header_metadata": "essay_with_header_metadata",
        "standard_freeform_essay": "standard_freeform_essay",
        "bulk_scanned_batch": "bulk_scanned_batch",
        "template": "template",
        "unknown": "unknown",
        "ifi_official_template_blank": "template",
        "essay_only": "standard_freeform_essay",
    }
    return legacy_map.get(low, "unknown")


def get_policy(record: dict, report: dict) -> ValidationPolicy:
    doc_type = _normalize_doc_type(record or {}, report or {})
    base = _POLICIES.get(doc_type, _POLICIES["unknown"])
    if doc_type == "unknown":
        doc_format = (record.get("format") or "").strip().lower()
        if doc_format in ("image_only", "hybrid"):
            return base._replace(min_ocr_confidence=0.50)
    return base


class DocClass(str, Enum):
    SINGLE_TYPED = "SINGLE_TYPED"
    SINGLE_SCANNED = "SINGLE_SCANNED"
    MULTI_PAGE_SINGLE = "MULTI_PAGE_SINGLE"
    BULK_SCANNED_BATCH = "BULK_SCANNED_BATCH"


class DocRole(str, Enum):
    CONTAINER = "container"
    DOCUMENT = "document"


def _coerce_doc_class(value: Any) -> DocClass | None:
    if isinstance(value, DocClass):
        return value
    if isinstance(value, str):
        try:
            return DocClass(value)
        except ValueError:
            return None
    return None


def _has_chunk_index(chunk_metadata: dict | None, record: dict | None) -> bool:
    if isinstance(chunk_metadata, dict) and chunk_metadata.get("chunk_index") is not None:
        return True
    if isinstance(record, dict) and record.get("chunk_index") is not None:
        return True
    return False


def classify_doc_role(
    record: dict | None,
    report: dict | None,
    chunk_metadata: dict | None = None,
) -> DocRole:
    if _has_chunk_index(chunk_metadata, record):
        return DocRole.DOCUMENT

    rec = record or {}
    rep = report or {}

    structure = (
        rec.get("analysis_structure")
        or rec.get("structure")
        or (rep.get("analysis") or {}).get("structure")
        or (rep.get("extraction_debug") or {}).get("analysis_structure")
    )
    doc_class = _coerce_doc_class(rec.get("doc_class"))
    if doc_class is None:
        doc_class = _coerce_doc_class((rep.get("extraction_debug") or {}).get("doc_class"))

    if bool(rec.get("is_container_parent")):
        return DocRole.CONTAINER
    if structure == "multi" or doc_class == DocClass.BULK_SCANNED_BATCH:
        return DocRole.CONTAINER
    return DocRole.DOCUMENT


def _normalize_token_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def normalize_grade(raw_grade):
    if raw_grade is None:
        return None, "missing"
    raw = str(raw_grade).strip()
    if not raw:
        return None, "missing"

    lowered = raw.casefold()
    if lowered in {"k", "kindergarten", "kinder"}:
        return "K", "kindergarten_alias"

    match = re.search(r"(-?\d+)", lowered)
    if not match:
        return None, "unparseable"
    val = int(match.group(1))
    if val == 0 or val < 0 or val > 12:
        return None, "invalid_range"
    if 1 <= val <= 12:
        if lowered == str(val):
            return val, "numeric"
        if "grade" in lowered:
            return val, "grade_prefix"
        if re.search(r"\d+(st|nd|rd|th)\b", lowered):
            return val, "ordinal"
        return val, "numeric_parse"
    return None, "unparseable"


def is_grade_missing(raw_grade) -> bool:
    return raw_grade is None or str(raw_grade).strip() == ""


def is_name_school_possible_swap(student_name, school_name) -> bool:
    if student_name is None or school_name is None:
        return False
    return _normalize_token_text(student_name) == _normalize_token_text(school_name)


def _normalize_school_text(value: str) -> str:
    text = (value or "").casefold()
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class SchoolReferenceValidator:
    def __init__(self, csv_path: str | None = None):
        env_path = os.environ.get("SCHOOL_REFERENCE_CSV_PATH")
        default_path = Path(__file__).resolve().parent / "reference_data" / "schools.csv"
        self.csv_path = Path(csv_path or env_path or default_path)
        self._rows = self._load_rows()
        self.reference_version = f"{self.csv_path.name}:{len(self._rows)}"
        self._normalized_rows = [_normalize_school_text(row) for row in self._rows]

    def _load_rows(self) -> list[str]:
        if not self.csv_path.exists():
            return []
        rows: list[str] = []
        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for item in reader:
                school = (item.get("school_name") or "").strip()
                if school:
                    rows.append(school)
        return rows

    def validate(self, school_name: str | None) -> dict:
        if not school_name or not str(school_name).strip():
            return {
                "matched": False,
                "method": "missing",
                "confidence": 0.0,
                "reference_version": self.reference_version,
            }
        normalized = _normalize_school_text(str(school_name))
        if normalized in self._normalized_rows:
            return {
                "matched": True,
                "method": "exact",
                "confidence": 1.0,
                "reference_version": self.reference_version,
            }

        best_ratio = 0.0
        for ref in self._normalized_rows:
            ratio = SequenceMatcher(None, normalized, ref).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
        if best_ratio >= 0.9:
            return {
                "matched": True,
                "method": "fuzzy",
                "confidence": round(float(best_ratio), 6),
                "reference_version": self.reference_version,
            }

        return {
            "matched": False,
            "method": "none",
            "confidence": round(float(best_ratio), 6),
            "reference_version": self.reference_version,
        }


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


def find_value_page(
    per_page_text: list[dict], value: str, start: int, end: int
) -> int | None:
    result = find_value_attribution(per_page_text, value, start, end)
    if not result:
        return None
    return result.get("page_index")


def find_grade_page(
    per_page_text: list[dict], grade: int | str, start: int, end: int
) -> int | None:
    result = find_grade_attribution(per_page_text, grade, start, end)
    if not result:
        return None
    return result.get("page_index")


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
    chunk_artifact_dir.mkdir(parents=True, exist_ok=True)
    with open(chunk_artifact_dir / "field_attribution_debug.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return True


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

