"""
Lightweight document analysis for format/structure classification and chunking.

Format: native_text | image_only | hybrid
Structure: single | multi | template | corrupt_or_incomplete
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional

import fitz  # PyMuPDF

from pipeline.ocr import get_ocr_provider, ocr_pdf_pages


@dataclass
class PageAnalysis:
    page_number: int
    text_layer_chars: int
    image_count: int
    ocr_top_strip_chars: int
    ocr_top_strip_confidence: float
    header_signature_score: float
    top_text: str


@dataclass
class ChunkRange:
    start_page: int
    end_page: int  # inclusive


@dataclass
class DocumentAnalysis:
    page_count: int
    format: str  # native_text | image_only | hybrid
    structure: str  # single | multi | template | corrupt_or_incomplete
    format_confidence: float
    structure_confidence: float
    chunk_ranges: List[ChunkRange]
    start_page_indices: List[int]
    pages: List[PageAnalysis]
    classifier_version: str = "v2"
    low_confidence_for_template: bool = False
    form_layout: str = "unknown"  # "unknown" | "ifi_official_typed" when consistent labels detected

    def to_json(self) -> str:
        data = asdict(self)
        data["pages"] = [asdict(p) for p in self.pages]
        data["chunk_ranges"] = [asdict(c) for c in self.chunk_ranges]
        return json.dumps(data, indent=2)


HEADER_KEYWORDS = [
    "student", "name",
    "grade", "grado",
    "school", "escuela",
    "teacher", "maestro", "maestra",
    "essay", "fatherhood", "illinois", "ifi",
]


def _header_signature_score(text: str) -> float:
    if not text:
        return 0.0
    lowered = text.lower()
    hits = sum(1 for kw in HEADER_KEYWORDS if kw in lowered)
    return hits / len(HEADER_KEYWORDS)


# Signature labels that define IFI official typed form layout (consistent across 22-IFI legacy and 26-IFI canonical form)
# Canonical form for this doc type: 26-IFI-Essay-Form-Eng-and-Spanish
IFI_TYPED_FORM_TOP_LABELS = [
    "ifi fatherhood essay contest",
    "illinois fatherhood initiative",
    "student's name",
    "student name",
    "nombre del estudiante",
    "grade",
    "grado",
    "school",
    "escuela",
]
IFI_TYPED_FORM_BOTTOM_LABELS = [
    "email",
    "phone",
    "father/father-figure name",
    "father/father-figure",
    "father-figure name",
    "nombre del padre",
    "figura paterna",
    "teléfono",
    "telefono",
]


def detect_ifi_official_typed_form(text: str) -> bool:
    """
    Detect IFI official typed form by layout and consistent labels.

    Typed form submissions have:
    - Top: Student's Name, Grade/Grado, School/Escuela (same place every time)
    - Bottom: Email, Phone, Father/Father-Figure Name

    Returns True when the text contains the expected label pattern.
    """
    if not text or len(text.strip()) < 50:
        return False
    # Normalize Unicode apostrophes (e.g. U+2019) to ASCII for matching
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    lowered = text.lower()
    top_hits = sum(1 for lbl in IFI_TYPED_FORM_TOP_LABELS if lbl in lowered)
    bottom_hits = sum(1 for lbl in IFI_TYPED_FORM_BOTTOM_LABELS if lbl in lowered)
    # Need contest/form identifier + header labels + footer labels
    has_contest = "ifi" in lowered and "fatherhood" in lowered
    if not has_contest:
        return False
    # At least 2 header labels (e.g. contest + student name, or student + grade/school)
    if top_hits < 2:
        return False
    # At least 1 footer label (email, phone, or father-figure) - consistent placement
    if bottom_hits < 1:
        return False
    return True


def _ocr_top_strip_if_needed(doc: fitz.Document, page_index: int, provider_name: str) -> tuple[str, float]:
    page = doc.load_page(page_index)
    rect = page.rect
    top_rect = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + rect.height * 0.25)
    pix = page.get_pixmap(clip=top_rect, dpi=200)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_img:
        tmp_img.write(pix.tobytes())
        tmp_path = tmp_img.name
    try:
        ocr = get_ocr_provider(provider_name)
        result = ocr.process_image(tmp_path)
        return result.text or "", result.confidence_avg or 0.0
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def extract_startpage_signals(page_text_top: str) -> dict:
    """
    Extract deterministic header signals used for template detection.
    """
    txt = (page_text_top or "").strip()
    lowered = txt.lower()
    has_boilerplate = any(
        phrase in lowered
        for phrase in [
            "ifi fatherhood essay contest",
            "illinois fatherhood initiative",
            "student name",
            "student's name",
            "father/father-figure",
            "writing about",
            "character maximum",
            "school / escuela",
            "school:",
            "grade / grado",
        ]
    )

    # Plausible student name: 2-5 tokens, alphabetic heavy, not boilerplate labels
    plausible_name = False
    tokens = [t for t in txt.replace("\n", " ").split() if t.isalpha()]
    if 2 <= len(tokens) <= 5:
        joined = " ".join(tokens).lower()
        if not any(label in joined for label in ["student", "essay", "fatherhood", "initiative", "contest"]):
            plausible_name = True

    plausible_grade = bool(
        (re.search(r"\b(k|kinder|kindergarten)\b", lowered))
        or (re.search(r"\b[1-9][0-2]?(st|nd|rd|th)?\s*grade\b", lowered))
        or (re.search(r"grade\s*[:\-]?\s*[1-9][0-2]?", lowered))
    )

    # Plausible school: has the word school/escuela with some extra text
    plausible_school = False
    if "school" in lowered or "escuela" in lowered:
        words = [w for w in txt.replace("\n", " ").split() if w.isalpha()]
        if len(words) >= 2:
            plausible_school = True

    return {
        "has_boilerplate": has_boilerplate,
        "has_plausible_student_name": plausible_name,
        "has_plausible_grade": plausible_grade,
        "has_plausible_school": plausible_school,
    }


def detect_template_document(pages: List[PageAnalysis], doc_format: str) -> tuple[bool, bool]:
    """
    Returns (is_template, blocked_low_confidence).
    """
    boilerplate_hits = 0
    has_filled_field = False
    low_conf_pages = 0

    for p in pages:
        signals = extract_startpage_signals(p.top_text)
        if signals["has_boilerplate"]:
            boilerplate_hits += 1
        if signals["has_plausible_student_name"] or signals["has_plausible_grade"] or signals["has_plausible_school"]:
            has_filled_field = True
        if doc_format in ("image_only", "hybrid") and (p.ocr_top_strip_confidence or 0.0) < 0.45:
            low_conf_pages += 1

    if doc_format in ("image_only", "hybrid") and low_conf_pages == len(pages):
        # Not confident enough to declare template
        return False, True

    if boilerplate_hits > 0 and not has_filled_field:
        return True, False

    return False, False


def analyze_document(pdf_path: str, ocr_provider_name: str = "google") -> DocumentAnalysis:
    doc = fitz.open(pdf_path)
    if len(doc) == 0:
        return DocumentAnalysis(
            page_count=0,
            format="corrupt_or_incomplete",
            structure="corrupt_or_incomplete",
            format_confidence=1.0,
            structure_confidence=1.0,
            chunk_ranges=[],
            start_page_indices=[],
            pages=[],
        )

    pages: List[PageAnalysis] = []
    text_pages = 0
    image_only_pages = 0

    top_strip_results = []
    # Precompute top-strip OCR for image_only/hybrid
    try:
        top_strip_results, _ = ocr_pdf_pages(pdf_path, pages=None, mode="top_strip", provider_name=ocr_provider_name, include_text=True)
    except Exception:
        top_strip_results = []

    for i in range(len(doc)):
        page = doc.load_page(i)
        text_layer = page.get_text("text")
        text_layer_chars = len(text_layer.strip())
        image_count = len(page.get_images(full=True))
        header_text = page.get_text("text", clip=fitz.Rect(
            page.rect.x0, page.rect.y0, page.rect.x1, page.rect.y0 + page.rect.height * 0.25
        ))
        ocr_strip_chars = 0
        ocr_strip_conf = 0.0
        top_text = header_text.strip()
        if text_layer_chars == 0 and top_strip_results:
            res = next((r for r in top_strip_results if r["page_index"] == i), None)
            if res:
                top_text = (res.get("text") or "").strip()
                ocr_strip_chars = len(top_text)
                ocr_strip_conf = res.get("confidence_avg") or 0.0
        header_score = _header_signature_score(top_text)

        pages.append(PageAnalysis(
            page_number=i + 1,
            text_layer_chars=text_layer_chars,
            image_count=image_count,
            ocr_top_strip_chars=ocr_strip_chars,
            ocr_top_strip_confidence=ocr_strip_conf,
            header_signature_score=header_score,
            top_text=top_text,
        ))
        if text_layer_chars > 0:
            text_pages += 1
        else:
            image_only_pages += 1

    page_count = len(pages)
    # Format classification
    if text_pages == page_count:
        doc_format = "native_text"
        fmt_conf = 0.9
    elif image_only_pages == page_count:
        doc_format = "image_only"
        fmt_conf = 0.9
    else:
        doc_format = "hybrid"
        fmt_conf = 0.9

    # Structure detection
    start_indices: List[int] = []
    for idx, p in enumerate(pages):
        # consider either text in header or OCR strip
        header_chars = p.text_layer_chars if p.text_layer_chars > 0 else p.ocr_top_strip_chars
        if p.header_signature_score >= 0.2 and header_chars >= 10:
            start_indices.append(idx)
    if not start_indices:
        start_indices = [0]
    else:
        if start_indices[0] != 0:
            start_indices.insert(0, 0)

    is_template, blocked_low_conf = detect_template_document(pages, doc_format)

    if blocked_low_conf:
        structure = "single"
        struct_conf = 0.5
    elif is_template:
        structure = "template"
        struct_conf = 0.85
    elif len(start_indices) > 1:
        structure = "multi"
        struct_conf = 0.8
    else:
        structure = "single"
        struct_conf = 0.8

    chunk_ranges: List[ChunkRange] = []
    for i, start_idx in enumerate(start_indices):
        end_idx = (start_indices[i + 1] - 1) if i + 1 < len(start_indices) else page_count - 1
        chunk_ranges.append(ChunkRange(start_page=start_idx, end_page=end_idx))

    # Detect IFI official typed form layout (consistent labels: top=name/grade/school, bottom=email/phone)
    form_layout = "unknown"
    if doc_format == "native_text" and page_count > 0:
        full_text_parts = []
        for i in range(page_count):
            p = doc.load_page(i)
            full_text_parts.append(p.get_text("text") or "")
        full_text = "\n\n".join(full_text_parts)
        if detect_ifi_official_typed_form(full_text):
            form_layout = "ifi_official_typed"

    return DocumentAnalysis(
        page_count=page_count,
        format=doc_format,
        structure=structure,
        format_confidence=fmt_conf,
        structure_confidence=struct_conf,
        chunk_ranges=chunk_ranges,
        start_page_indices=start_indices,
        pages=pages,
        low_confidence_for_template=blocked_low_conf,
        form_layout=form_layout,
    )


def make_chunk_submission_id(base_submission_id: str, chunk_index: int) -> str:
    h = hashlib.sha256(f"{base_submission_id}:{chunk_index}".encode()).hexdigest()
    return h[:12]
