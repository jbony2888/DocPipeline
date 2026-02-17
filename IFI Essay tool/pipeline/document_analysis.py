"""
Lightweight document analysis for format/structure classification and chunking.

Format: native_text | image_only | hybrid
Structure: single | multi | template | corrupt_or_incomplete
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass, asdict, field
from typing import List, Tuple, Optional

import fitz  # PyMuPDF

from pipeline.ocr import get_ocr_provider, ocr_pdf_pages
from pipeline.schema import DocClass

logger = logging.getLogger(__name__)


@dataclass
class PageAnalysis:
    page_number: int
    text_layer_chars: int
    image_count: int
    ocr_top_strip_chars: int
    ocr_top_strip_confidence: float
    header_signature_score: float
    top_text: str
    dark_bands: List[Tuple[float, float]] = field(default_factory=list)  # (y_start_ratio, y_end_ratio) 0-1


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
    form_layout: str = "unknown"  # "unknown" | "ifi_official_typed" | "ifi_official_scanned" when consistent labels detected
    is_scanned_multi_submission: bool = False  # True when format=image_only, structure=multi, requires OCR for handwritten essays
    doc_class: DocClass = DocClass.SINGLE_TYPED  # Formal classification (assigned before extraction)

    def to_json(self) -> str:
        data = asdict(self)
        data["pages"] = [asdict(p) for p in self.pages]
        data["chunk_ranges"] = [asdict(c) for c in self.chunk_ranges]
        # Serialize DocClass enum for JSON
        dc = data.get("doc_class")
        if hasattr(dc, "value"):
            data["doc_class"] = dc.value
        return json.dumps(data, indent=2)


HEADER_KEYWORDS = [
    "student", "name",
    "grade", "grado",
    "school", "escuela",
    "teacher", "maestro", "maestra",
    "essay", "fatherhood", "illinois", "ifi",
]

# Relaxed keywords for scanned/handwritten OCR (common substitutions: l->1, 0->O, missing chars)
HEADER_KEYWORDS_RELAXED = HEADER_KEYWORDS + [
    "studnt", "studen", "studet",  # student
    "garde", "grad", "grade",      # grade
    "schol", "schoo", "schol",     # school
    "escue", "escuel",             # escuela
    "essay", "fahter", "father",   # essay, father
    "illinois", "initiative",
]


def _header_signature_score(text: str) -> float:
    if not text:
        return 0.0
    lowered = text.lower()
    hits = sum(1 for kw in HEADER_KEYWORDS if kw in lowered)
    return hits / len(HEADER_KEYWORDS)


def _header_signature_score_relaxed(text: str) -> float:
    """
    Relaxed header score for scanned/handwritten OCR output.
    Uses expanded keyword set to tolerate OCR errors (e.g. studnt, garde, schol).
    """
    if not text:
        return 0.0
    lowered = text.lower()
    hits = sum(1 for kw in HEADER_KEYWORDS_RELAXED if kw in lowered)
    return min(1.0, hits / max(1, len(HEADER_KEYWORDS)))


# Signature labels that define IFI official typed form layout (consistent across 22-IFI legacy and 26-IFI).
# Standard layout for both PDF and scanned image: 26-IFI-Essay-Form-Eng-and-Spanish (filled: 26-IFI-Essay-Form-Eng-and-Spanish-filled.pdf).
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


def classify_document(
    doc_format: str,
    structure: str,
    page_count: int,
    chunk_count: int,
) -> "DocClass":
    """
    Assign formal document classification. Runs before field extraction.
    Every submission has exactly one DocClass; no fallback to unknown.
    """
    if structure == "multi" and chunk_count > 1:
        return DocClass.BULK_SCANNED_BATCH
    if structure == "single" and page_count > 1:
        return DocClass.MULTI_PAGE_SINGLE
    if doc_format == "native_text" and page_count == 1:
        return DocClass.SINGLE_TYPED
    if doc_format in ("image_only", "hybrid") and page_count == 1:
        return DocClass.SINGLE_SCANNED
    # Template or corrupt: map by format
    if doc_format == "native_text":
        return DocClass.SINGLE_TYPED
    return DocClass.SINGLE_SCANNED


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


# Relaxed labels for scanned/handwritten OCR (typos, partial matches)
IFI_SCANNED_TOP_LABELS = IFI_TYPED_FORM_TOP_LABELS + [
    "student name", "studnt", "nombre del estudiante", "estudiante",
    "grado", "grade", "garde", "grad",
    "escuela", "school", "schol",
]
IFI_SCANNED_BOTTOM_LABELS = IFI_TYPED_FORM_BOTTOM_LABELS + [
    "email", "phone", "telefono", "father", "padre", "figura",
]

# Labels that count as "Student Name" anchor for bulk-batch heuristic (one per form)
STUDENT_NAME_ANCHOR_LABELS = [
    "student's name",
    "student name",
    "students name",
    "nombre del estudiante",
    "estudiante",
]
STUDENT_NAME_ANCHOR_RELAXED = STUDENT_NAME_ANCHOR_LABELS + [
    "studnt name", "student nam", "nombre del estud",
]


def _count_student_name_anchors_on_page(top_text: str, use_relaxed: bool) -> int:
    """
    Count occurrences of Student Name labels in the top strip text (anchors per form).
    Returns 1 if this page has at least one anchor, else 0.
    """
    if not (top_text or "").strip():
        return 0
    lowered = top_text.lower().replace("\u2019", "'")
    labels = STUDENT_NAME_ANCHOR_RELAXED if use_relaxed else STUDENT_NAME_ANCHOR_LABELS
    for lbl in labels:
        if lbl in lowered:
            return 1
    return 0


def _student_name_anchor_counts_per_page(pages: List[PageAnalysis], doc_format: str) -> List[int]:
    """Return one count per page: 1 if that page's top strip has a Student Name anchor, else 0."""
    use_relaxed = doc_format in ("image_only", "hybrid")
    return [_count_student_name_anchors_on_page(p.top_text, use_relaxed) for p in pages]


def _layout_repeats_in_first_3_pages(pages: List[PageAnalysis], doc_format: str) -> bool:
    """
    True if the IFI header (contest + header labels) appears on at least 2 of the first 3 pages.
    Single multi-page essays have the header only on page 0; batch docs repeat it per submission.
    """
    if len(pages) < 2:
        return False
    check = pages[: min(3, len(pages))]
    use_relaxed = doc_format in ("image_only", "hybrid")
    score_threshold = 0.15 if use_relaxed else 0.2
    chars_threshold = 5 if use_relaxed else 10
    pages_with_header = 0
    for p in check:
        header_chars = p.text_layer_chars if p.text_layer_chars > 0 else p.ocr_top_strip_chars
        score = _header_signature_score_relaxed(p.top_text) if use_relaxed else p.header_signature_score
        has_contest = "ifi" in (p.top_text or "").lower() and "father" in (p.top_text or "").lower()
        if score >= score_threshold and header_chars >= chars_threshold and has_contest:
            pages_with_header += 1
    return pages_with_header >= 2


def _is_bulk_scanned_batch_heuristic(
    page_count: int,
    pages: List[PageAnalysis],
    doc_format: str,
) -> Tuple[bool, str]:
    """
    Heuristic: BULK_SCANNED_BATCH when page_count > 1, layout repeats in first 3 pages,
    and multiple Student Name anchors across pages. Returns (is_bulk, reason).
    """
    if page_count <= 1:
        return False, "page_count<=1"
    if not pages:
        return False, "no_pages"
    anchor_counts = _student_name_anchor_counts_per_page(pages, doc_format)
    total_anchors = sum(anchor_counts)
    pages_with_anchor = sum(1 for c in anchor_counts if c > 0)
    if total_anchors < 2 or pages_with_anchor < 2:
        return False, f"anchors total={total_anchors} pages_with_anchor={pages_with_anchor}"
    if not _layout_repeats_in_first_3_pages(pages, doc_format):
        return False, "layout_does_not_repeat_in_first_3"
    return True, "page_count>1, layout_repeats, multiple_student_name_anchors"


def detect_ifi_official_scanned_form(text: str) -> bool:
    """
    Detect IFI official form from scanned/handwritten OCR text.
    Uses relaxed matching to tolerate OCR errors and handwriting variability.
    """
    if not text or len(text.strip()) < 30:
        return False
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    lowered = text.lower()
    top_hits = sum(1 for lbl in IFI_SCANNED_TOP_LABELS if lbl in lowered)
    bottom_hits = sum(1 for lbl in IFI_SCANNED_BOTTOM_LABELS if lbl in lowered)
    has_contest = ("ifi" in lowered and "fatherhood" in lowered) or ("essay" in lowered and "father" in lowered)
    if not has_contest:
        return False
    if top_hits < 1:
        return False
    if bottom_hits < 1:
        return False
    return True


def detect_dark_horizontal_bands(
    doc: fitz.Document, page_index: int,
    darkness_threshold: float = 0.35,
    min_band_height_ratio: float = 0.01,
    min_band_width_ratio: float = 0.5,
    sample_step: int = 4,
) -> List[Tuple[float, float]]:
    """
    Detect dark horizontal bands (black/gray separators) in a rendered page.
    Returns list of (y_start_ratio, y_end_ratio) in 0-1 range (top to bottom).
    Dark bands can mark boundaries between submissions or fields.
    """
    page = doc.load_page(page_index)
    # Render as grayscale for luminance
    pix = page.get_pixmap(dpi=150, colorspace=fitz.csGRAY, alpha=False)
    w, h = pix.width, pix.height
    if w <= 0 or h <= 0:
        return []
    samples = pix.samples
    if not samples:
        return []
    # Row luminance: for each row, mean pixel value (0=black, 255=white)
    bands: List[Tuple[float, float]] = []
    in_band = False
    band_start_y = 0
    band_pixels_ratio = min_band_width_ratio  # require dark across this fraction of width
    dark_value = int(255 * (1 - darkness_threshold))  # below this = dark
    step = max(1, sample_step)
    for y in range(0, h, step):
        row_start = y * w
        row_end = min((y + step) * w, len(samples))
        if row_end <= row_start:
            continue
        row_vals = list(samples[row_start:row_end])
        mean_val = sum(row_vals) / len(row_vals) if row_vals else 255
        is_dark = mean_val < dark_value
        # Also check horizontal spread: sample center portion
        center_start = int(w * (1 - band_pixels_ratio) / 2)
        center_end = int(w * (1 + band_pixels_ratio) / 2)
        center_vals = []
        for yy in range(y, min(y + step, h)):
            for x in range(center_start, min(center_end, w)):
                idx = yy * w + x
                if idx < len(samples):
                    center_vals.append(samples[idx])
        center_dark = (sum(center_vals) / len(center_vals)) < dark_value if center_vals else False
        if is_dark or center_dark:
            if not in_band:
                in_band = True
                band_start_y = y / h
        else:
            if in_band:
                band_end_y = (y + step) / h
                if (band_end_y - band_start_y) >= min_band_height_ratio:
                    bands.append((band_start_y, min(1.0, band_end_y)))
                in_band = False
    if in_band:
        bands.append((band_start_y, 1.0))
    return bands


def _has_dark_band_near_top(dark_bands: List[Tuple[float, float]], top_zone: float = 0.15) -> bool:
    """True if a dark band intersects the top zone (suggests content below is new submission)."""
    for y0, y1 in dark_bands:
        if y0 < top_zone:
            return True
    return False


def _has_dark_band_near_bottom(dark_bands: List[Tuple[float, float]], bottom_zone: float = 0.85) -> bool:
    """True if a dark band is in bottom zone (suggests end of submission)."""
    for y0, y1 in dark_bands:
        mid = (y0 + y1) / 2
        if mid > bottom_zone:
            return True
    return False


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
        # Lower threshold (0.35) for scanned/handwritten OCR - handwriting often 0.4-0.6
        if doc_format in ("image_only", "hybrid") and (p.ocr_top_strip_confidence or 0.0) < 0.35:
            low_conf_pages += 1

    if doc_format in ("image_only", "hybrid") and low_conf_pages == len(pages):
        # Not confident enough to declare template (all pages very low OCR confidence)
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

        dark_bands: List[Tuple[float, float]] = []
        if text_layer_chars == 0:
            try:
                dark_bands = detect_dark_horizontal_bands(doc, i)
            except Exception:
                pass

        pages.append(PageAnalysis(
            page_number=i + 1,
            text_layer_chars=text_layer_chars,
            image_count=image_count,
            ocr_top_strip_chars=ocr_strip_chars,
            ocr_top_strip_confidence=ocr_strip_conf,
            header_signature_score=header_score,
            top_text=top_text,
            dark_bands=dark_bands,
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

    # Structure detection (use relaxed scoring for scanned/handwritten image_only/hybrid)
    start_indices: List[int] = []
    use_relaxed = doc_format in ("image_only", "hybrid")
    score_threshold = 0.15 if use_relaxed else 0.2
    chars_threshold = 5 if use_relaxed else 10
    for idx, p in enumerate(pages):
        header_chars = p.text_layer_chars if p.text_layer_chars > 0 else p.ocr_top_strip_chars
        score = _header_signature_score_relaxed(p.top_text) if use_relaxed else p.header_signature_score
        if score >= score_threshold and header_chars >= chars_threshold:
            start_indices.append(idx)
    if not start_indices:
        start_indices = [0]
    else:
        if start_indices[0] != 0:
            start_indices.insert(0, 0)

    is_template, blocked_low_conf = detect_template_document(pages, doc_format)

    # Scanned multi-submission heuristic: IFI forms are ~2-3 pages each.
    # If image_only, 6+ pages, only 1 start, and not blocked by low confidence, look for periodic header-like pages
    if (
        use_relaxed
        and not blocked_low_conf
        and page_count >= 6
        and len(start_indices) == 1
    ):
        periodic_starts = [0]
        for idx in range(2, page_count, 2):  # every 2nd page as potential submission start
            if idx >= page_count:
                break
            p = pages[idx]
            score = _header_signature_score_relaxed(p.top_text)
            if score >= 0.1 and (p.ocr_top_strip_chars or 0) >= 3:
                periodic_starts.append(idx)
        if len(periodic_starts) >= 2:
            start_indices = periodic_starts

    # Dark band refinement: use black/dark horizontal separators as submission boundaries.
    # When every page was marked as start (over-chunking), prefer pages with dark band at top
    # (new submission) vs pages without (continuation of previous).
    if (
        use_relaxed
        and not blocked_low_conf
        and page_count >= 4
        and len(start_indices) == page_count
    ):
        pages_with_dark_top = sum(
            1 for p in pages if p.dark_bands and _has_dark_band_near_top(p.dark_bands)
        )
        if pages_with_dark_top >= 2:
            refined = [0]
            for idx in range(1, page_count):
                if pages[idx].dark_bands and _has_dark_band_near_top(pages[idx].dark_bands):
                    refined.append(idx)
            if len(refined) >= 2:
                start_indices = refined

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

    # Detect IFI official form layout
    form_layout = "unknown"
    if doc_format == "native_text" and page_count > 0:
        full_text_parts = []
        for i in range(page_count):
            p = doc.load_page(i)
            full_text_parts.append(p.get_text("text") or "")
        full_text = "\n\n".join(full_text_parts)
        if detect_ifi_official_typed_form(full_text):
            form_layout = "ifi_official_typed"
    elif doc_format in ("image_only", "hybrid") and page_count > 0:
        # Scanned/handwritten: use OCR top-strip text aggregated across pages
        ocr_text_parts = [p.top_text for p in pages if p.top_text]
        if ocr_text_parts:
            aggregated_ocr = "\n\n".join(ocr_text_parts)
            if detect_ifi_official_scanned_form(aggregated_ocr):
                form_layout = "ifi_official_scanned"

    is_scanned_multi = (
        doc_format == "image_only"
        and structure == "multi"
        and len(chunk_ranges) > 1
    )

    doc_class = classify_document(
        doc_format=doc_format,
        structure=structure,
        page_count=page_count,
        chunk_count=len(chunk_ranges),
    )

    # Explicit bulk-batch heuristic: multi-page + repeated layout + multiple Student Name anchors
    is_bulk_heuristic, bulk_reason = _is_bulk_scanned_batch_heuristic(page_count, pages, doc_format)
    if is_bulk_heuristic:
        doc_class = DocClass.BULK_SCANNED_BATCH
        logger.info(
            "doc_class=BULK_SCANNED_BATCH (heuristic: %s) page_count=%s structure=%s chunk_count=%s",
            bulk_reason, page_count, structure, len(chunk_ranges),
        )
    else:
        logger.info(
            "doc_class=%s (bulk_heuristic=False: %s) page_count=%s structure=%s chunk_count=%s",
            doc_class.value, bulk_reason, page_count, structure, len(chunk_ranges),
        )

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
        is_scanned_multi_submission=is_scanned_multi,
        doc_class=doc_class,
    )


def get_page_level_ranges_for_batch(page_count: int) -> List[ChunkRange]:
    """
    Return one ChunkRange per page for BULK_SCANNED_BATCH splitting.
    Used so each page becomes an independent submission (no chunk-level extraction in batch mode).
    """
    return [ChunkRange(start_page=i, end_page=i) for i in range(page_count)]


def make_chunk_submission_id(base_submission_id: str, chunk_index: int) -> str:
    h = hashlib.sha256(f"{base_submission_id}:{chunk_index}".encode()).hexdigest()
    return h[:12]
