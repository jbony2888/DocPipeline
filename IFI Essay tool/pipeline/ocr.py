"""
OCR provider abstraction with stub and Google Cloud Vision implementations.
"""

import io
import json
import os
import tempfile
from pathlib import Path
from typing import Protocol
from pipeline.schema import OcrResult
import fitz


def _confidence_stats(confidences: list[float], low_threshold: float = 0.65) -> tuple[float, float, int]:
    """
    Compute min, p10 percentile, and low confidence page count.
    Returns (min_conf, p10_conf, low_conf_count)
    """
    if not confidences:
        return 0.0, 0.0, 0
    sorted_conf = sorted(confidences)
    min_conf = sorted_conf[0]
    p10_index = max(0, int(len(sorted_conf) * 0.1) - 1)
    p10_conf = sorted_conf[p10_index]
    low_conf_count = sum(1 for c in confidences if c < low_threshold)
    return float(min_conf), float(p10_conf), int(low_conf_count)


def extract_pdf_text_layer(
    pdf_path: str,
    pages: list[int] | None = None,
    mode: str = "full",
    include_text: bool = True,
) -> tuple[list[dict], int]:
    """
    Extract text from PDF using the native text layer only (no OCR).
    Use for typed form submissions (format native_text).

    Returns (per_page_results, total_pages) with same shape as ocr_pdf_pages:
      each dict: page_index, text, confidence_avg=1.0, confidence_min, confidence_p10,
      low_conf_page_count=0, char_count
    """
    doc = fitz.open(pdf_path)
    page_indices = pages if pages is not None else list(range(len(doc)))
    results = []
    for idx in page_indices:
        page = doc.load_page(idx)
        rect = page.rect
        if mode == "top_strip":
            clip = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + rect.height * 0.25)
            text = page.get_text("text", clip=clip)
        else:
            text = page.get_text("text")
        text = (text or "").strip()
        # Merge form field values into text so extraction sees them (filled AcroForm fields).
        # Match exact 26-IFI form widget names so prepended lines are at top of text for extraction.
        form_field_values = None
        if idx == 0 and mode == "full":
            form_lines = []
            form_field_values = {}
            for w in page.widgets():
                v = (w.field_value or "").strip()
                if not v or w.field_type == 5:  # skip radio/checkbox unless we need state
                    continue
                name = w.field_name
                form_field_values[name] = v
                if name in ("Student's Name", "Grade", "School", "Essay", "Dad's Response"):
                    form_lines.append(f"{name}: {v}")
                elif name == "Dad's Name":
                    form_lines.append(f"Father/Father-Figure Name: {v}")
                elif name == "Dad's Email":
                    form_lines.append(f"Email: {v}")
                elif name == "Dad's Phone":
                    form_lines.append(f"Phone: {v}")
            if form_lines:
                text = "\n".join(form_lines) + "\n\n" + text
            if not form_field_values:
                form_field_values = None
        char_count = len(text)
        # Native text = high confidence
        entry = {
            "page_index": idx,
            "confidence_avg": 1.0,
            "confidence_min": 1.0,
            "confidence_p10": 1.0,
            "low_conf_page_count": 0,
            "char_count": char_count,
        }
        if include_text:
            entry["text"] = text
        if form_field_values is not None:
            entry["form_field_values"] = form_field_values
        results.append(entry)
    doc.close()
    return results, len(results)


def get_ocr_result_from_pdf_text_layer(pdf_path: str) -> OcrResult | None:
    """
    Build an OcrResult from the PDF text layer only (no OCR).
    Returns None only if the PDF has no pages or page 0 has no text (caller should use OCR).
    Other pages may be empty (e.g. image-only); we still use page-0 form fields and text.
    Use for typed form submissions (native_text) to avoid OCR.
    """
    try:
        per_page, _ = extract_pdf_text_layer(pdf_path, pages=None, mode="full", include_text=True)
    except Exception:
        return None
    if not per_page:
        return None
    sorted_pages = sorted(per_page, key=lambda x: int(x.get("page_index", 0)))
    # Require only page 0 to have text so we can use form fields and avoid OCR when page 2 is image-only
    page0_text = (sorted_pages[0].get("text") or "").strip()
    if not page0_text:
        return None
    texts = []
    form_field_values = None
    for p in sorted_pages:
        t = (p.get("text") or "").strip()
        texts.append(t if t else "")
        if form_field_values is None and p.get("form_field_values"):
            form_field_values = p["form_field_values"]
    full_text = "\n\n".join(texts)
    lines = full_text.split("\n") if full_text else []
    return OcrResult(
        text=full_text,
        confidence_avg=1.0,
        confidence_min=1.0,
        confidence_p10=1.0,
        low_conf_page_count=0,
        lines=lines,
        form_field_values=form_field_values,
    )


def ocr_pdf_pages(
    pdf_path: str,
    pages: list[int] | None = None,
    mode: str = "full",
    provider_name: str = "google",
    provider: "OcrProvider | None" = None,
    include_text: bool = False,
) -> tuple[list[dict], int]:
    """
    OCR selected pages of a PDF (default all). Mode can be:
      - full: render full page
      - top_strip: render top 25% of page (for header detection)
    Returns (per_page_results, total_pages_ocrd)
    Each per_page_result: {page_index, text, confidence_avg, confidence_min, confidence_p10, low_conf_page_count, char_count}
    """
    doc = fitz.open(pdf_path)
    page_indices = pages if pages is not None else list(range(len(doc)))
    provider = provider or get_ocr_provider(provider_name)
    results = []
    for idx in page_indices:
        page = doc.load_page(idx)
        rect = page.rect
        if mode == "top_strip":
            clip = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + rect.height * 0.25)
        else:
            clip = rect
        pix = page.get_pixmap(clip=clip, dpi=300)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_img:
            tmp_img.write(pix.tobytes())
            tmp_path = tmp_img.name
        try:
            ocr_res = provider.process_image(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        confs = [ocr_res.confidence_avg or 0.0]
        min_conf, p10_conf, low_conf = _confidence_stats(confs)
        entry = {
            "page_index": idx,
            "confidence_avg": ocr_res.confidence_avg,
            "confidence_min": min_conf,
            "confidence_p10": p10_conf,
            "low_conf_page_count": low_conf,
            "char_count": len((ocr_res.text or "").strip()),
        }
        if include_text:
            entry["text"] = ocr_res.text or ""
        results.append(entry)

    # Guardrail: per-page OCR output must be 1:1 with requested page indices.
    if len(results) != len(page_indices):
        raise AssertionError(
            f"OCR page result count mismatch for {pdf_path}: "
            f"expected={len(page_indices)} actual={len(results)}"
        )
    expected_indices = set(page_indices)
    actual_indices = {int(r.get("page_index", -1)) for r in results}
    if actual_indices != expected_indices:
        raise AssertionError(
            f"OCR page indices mismatch for {pdf_path}: "
            f"expected={sorted(expected_indices)} actual={sorted(actual_indices)}"
        )
    return results, len(page_indices)


class OcrProvider(Protocol):
    """Protocol for OCR providers."""
    
    def process_image(self, image_path: str) -> OcrResult:
        """Process an image and return OCR results."""
        ...


class StubOcrProvider:
    """
    Stub OCR provider that simulates handwritten text recognition.
    Returns realistic handwritten-style output with typical OCR characteristics.
    """
    
    def process_image(self, image_path: str) -> OcrResult:
        """
        Simulates OCR processing of handwritten essay submission.
        
        Args:
            image_path: Path to image file (not actually read in stub)
            
        Returns:
            OcrResult with simulated handwritten text
        """
        # Simulate typical handwritten essay submission
        simulated_text = """Name: Andrick Vargas Hernandez
School: Lincoln Middle School
Grade: 8

My father has always been someone I look up to. He came to this country
with nothing but hope and determination. When I was young, I remember
watching him leave for work before sunrise and return after dark.

He worked construction jobs, sometimes two or three at a time, to make
sure our family had everything we needed. Even when he was tired, he
would help me with my homework and tell me stories about his childhood
in Mexico.

What inspires me most is how he never complained. He taught me that
hard work and education are the keys to success. Because of him, I
want to become an engineer and build things that help people, just
like he does every day.

My father may not have a college degree, but he is the smartest and
bravest person I know. He is my hero."""

        lines = simulated_text.strip().split('\n')
        confidences = [0.65]
        min_conf, p10_conf, low_conf = _confidence_stats(confidences)
        return OcrResult(
            text=simulated_text.strip(),
            confidence_avg=0.65,  # Typical for handwriting
            confidence_min=min_conf,
            confidence_p10=p10_conf,
            low_conf_page_count=low_conf,
            lines=lines
        )


def compute_ocr_quality_score(text: str) -> float:
    """
    Compute a 0-1 quality score using heuristics on extracted text.
    
    This provides a deterministic confidence-like metric when OCR vendors
    don't provide consistent confidence values.
    
    Heuristics:
        - alpha_ratio: proportion of letters in non-whitespace chars
        - garbage_ratio: proportion of non-alphanumeric symbols in non-whitespace chars
        - score = (alpha_ratio * 0.8) + ((1 - garbage_ratio) * 0.2)
    
    Args:
        text: Extracted OCR text
        
    Returns:
        Quality score between 0.0 and 1.0
    """
    if not text or not text.strip():
        return 0.0
    
    # Count character types
    non_whitespace_chars = [c for c in text if not c.isspace()]
    
    if not non_whitespace_chars:
        return 0.0
    
    total_non_ws = len(non_whitespace_chars)
    alpha_count = sum(1 for c in non_whitespace_chars if c.isalpha())
    alnum_count = sum(1 for c in non_whitespace_chars if c.isalnum())
    
    # Compute ratios
    alpha_ratio = alpha_count / total_non_ws
    garbage_ratio = (total_non_ws - alnum_count) / total_non_ws
    
    # Weighted score
    score = (alpha_ratio * 0.8) + ((1 - garbage_ratio) * 0.2)
    
    # Clamp to [0, 1]
    return max(0.0, min(1.0, score))


class GoogleVisionOcrProvider:
    """
    Google Cloud Vision OCR provider with handwriting support.
    Supports both images (PNG/JPG) and PDFs (renders first page).
    
    Credentials can be provided in two ways:
        1. GOOGLE_APPLICATION_CREDENTIALS env var (file path to JSON)
        2. GOOGLE_CLOUD_VISION_CREDENTIALS_JSON env var (JSON content directly)
    
    Also requires:
        - Cloud Vision API enabled in Google Cloud Console
        - Billing enabled (if required)
    """
    
    def __init__(self):
        """
        Initialize Google Cloud Vision client.
        
        Supports two credential methods:
        1. File path: GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
        2. JSON content: GOOGLE_CLOUD_VISION_CREDENTIALS_JSON='{"type":"service_account",...}'
        """
        try:
            from google.cloud import vision
            from google.oauth2 import service_account
            
            # Check for JSON content in environment variable
            credentials_json = os.environ.get('GOOGLE_CLOUD_VISION_CREDENTIALS_JSON')
            
            if credentials_json:
                # Load credentials from JSON string
                try:
                    credentials_dict = json.loads(credentials_json)
                    credentials = service_account.Credentials.from_service_account_info(
                        credentials_dict
                    )
                    self.client = vision.ImageAnnotatorClient(credentials=credentials)
                except json.JSONDecodeError:
                    # JSON invalid (e.g. .env escaping issues) - fall back to file
                    credentials_json = None
            if not credentials_json:
                # Use standard GOOGLE_APPLICATION_CREDENTIALS (file path)
                self.client = vision.ImageAnnotatorClient()
                
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize Google Cloud Vision client: {e}\n\n"
                "Credentials can be provided in two ways:\n"
                "1. File path: GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json\n"
                "2. JSON content: GOOGLE_CLOUD_VISION_CREDENTIALS_JSON='{...}'\n\n"
                "Also ensure Cloud Vision API is enabled in Google Cloud Console."
            )
    
    def process_image(self, image_path: str) -> OcrResult:
        """
        Process an image or PDF and return OCR results.
        
        For PDFs: renders first page to PNG, then OCRs the image.
        For images: sends bytes directly to Vision API.
        
        Args:
            image_path: Path to image or PDF file
            
        Returns:
            OcrResult with extracted text and quality score
        """
        from google.cloud import vision
        
        file_path = Path(image_path)
        
        extracted_texts = []
        confidences = []
        if file_path.suffix.lower() == '.pdf':
            images = self._render_pdf_pages_to_png(image_path)
        else:
            with open(image_path, 'rb') as f:
                images = [f.read()]

        for image_bytes in images:
            image = vision.Image(content=image_bytes)
            response = self.client.document_text_detection(image=image)
            if response.error.message:
                raise RuntimeError(
                    f"Google Cloud Vision API error: {response.error.message}"
                )
            page_text = ""
            if response.full_text_annotation and response.full_text_annotation.text:
                page_text = response.full_text_annotation.text.strip()
            elif response.text_annotations:
                page_text = response.text_annotations[0].description.strip()
            if page_text:
                extracted_texts.append(page_text)
                confidences.append(compute_ocr_quality_score(page_text))

        extracted_text = "\n".join(extracted_texts)
        quality_score = sum(confidences) / len(confidences) if confidences else 0.0
        min_conf, p10_conf, low_conf = _confidence_stats(confidences)
        lines = extracted_text.split('\n') if extracted_text else []

        return OcrResult(
            text=extracted_text,
            confidence_avg=quality_score,
            confidence_min=min_conf,
            confidence_p10=p10_conf,
            low_conf_page_count=low_conf,
            lines=lines
        )
    
    def _render_pdf_pages_to_png(self, pdf_path: str) -> list[bytes]:
        """
        Render all pages of PDF to PNG bytes using PyMuPDF.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError(
                "PyMuPDF not installed. Install with: pip install PyMuPDF"
            )
        
        pdf_document = fitz.open(pdf_path)
        if len(pdf_document) == 0:
            raise ValueError(f"PDF file is empty: {pdf_path}")
        
        images: list[bytes] = []
        for page in pdf_document:
            pixmap = page.get_pixmap(dpi=300)
            images.append(pixmap.tobytes("png"))
        pdf_document.close()
        return images


class EasyOcrProvider:
    """
    EasyOCR provider - open source, runs locally, no API keys needed.
    Excellent for handwriting recognition, supports 80+ languages.
    
    Advantages:
        - Free and open source
        - No API keys or credentials required
        - Runs entirely locally (no internet needed after model download)
        - Good handwriting support
        - GPU acceleration if available
    
    First run will download models (~100MB), then cached for future use.
    """
    
    def __init__(self):
        """
        Initialize EasyOCR reader.
        
        Downloads models on first use (~100MB for English).
        Models are cached in ~/.EasyOCR/ for subsequent runs.
        """
        try:
            import easyocr
            
            # Initialize reader for English and Spanish
            # GPU will be used automatically if available (CUDA/MPS)
            # Set verbose=False to reduce console output
            self.reader = easyocr.Reader(
                ['en', 'es'],  # English and Spanish support
                gpu=True,  # Auto-detects GPU availability
                verbose=False
            )
            
        except ImportError:
            raise RuntimeError(
                "EasyOCR not installed. Install with: pip install easyocr torch torchvision"
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize EasyOCR: {e}\n"
                "First run downloads models (~100MB). Ensure internet connection."
            )
    
    def process_image(self, image_path: str) -> OcrResult:
        """
        Process an image or PDF and return OCR results.
        
        For PDFs: renders first page to PNG, then OCRs the image.
        For images: processes directly.
        
        Args:
            image_path: Path to image or PDF file
            
        Returns:
            OcrResult with extracted text and quality score
        """
        file_path = Path(image_path)
        
        # Handle PDF files
        if file_path.suffix.lower() == '.pdf':
            image_bytes = self._render_pdf_to_png(image_path)
            # EasyOCR can work with bytes via numpy array
            import numpy as np
            from PIL import Image
            
            image_pil = Image.open(io.BytesIO(image_bytes))
            image_array = np.array(image_pil)
            
            # Run OCR on numpy array
            results = self.reader.readtext(image_array)
        else:
            # Handle image files - EasyOCR can read directly from path
            results = self.reader.readtext(str(image_path))
        
        # EasyOCR returns list of ([box], text, confidence)
        # Extract text and compute average confidence
        if not results:
            return OcrResult(
                text="",
                confidence_avg=0.0,
                lines=[]
            )
        
        # Combine all text pieces, sorted by vertical position (top to bottom)
        # Each result: (bounding_box, text, confidence)
        sorted_results = sorted(results, key=lambda x: x[0][0][1])  # Sort by top-left Y
        
        extracted_texts = [text for (_, text, _) in sorted_results]
        extracted_text = '\n'.join(extracted_texts)
        
        # Compute average confidence from EasyOCR confidences
        confidences = [conf for (_, _, conf) in sorted_results]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        # Also compute our quality score for consistency
        quality_score = compute_ocr_quality_score(extracted_text)
        
        # Use weighted average: 70% EasyOCR confidence, 30% our quality score
        final_confidence = (avg_confidence * 0.7) + (quality_score * 0.3)
        
        # Split into lines for compatibility
        lines = extracted_text.split('\n') if extracted_text else []
        
        min_conf, p10_conf, low_conf = _confidence_stats([final_confidence])
        return OcrResult(
            text=extracted_text,
            confidence_avg=final_confidence,
            confidence_min=min_conf,
            confidence_p10=p10_conf,
            low_conf_page_count=low_conf,
            lines=lines
        )
    
    def _render_pdf_to_png(self, pdf_path: str) -> bytes:
        """
        Render first page of PDF to PNG bytes using PyMuPDF.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            PNG image bytes
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError(
                "PyMuPDF not installed. Install with: pip install PyMuPDF"
            )
        
        # Open PDF and render first page
        pdf_document = fitz.open(pdf_path)
        
        if len(pdf_document) == 0:
            raise ValueError(f"PDF file is empty: {pdf_path}")
        
        # Render first page to pixmap (higher DPI for better OCR)
        page = pdf_document[0]
        pixmap = page.get_pixmap(dpi=300)
        
        # Convert pixmap to PNG bytes
        png_bytes = pixmap.tobytes("png")
        
        pdf_document.close()
        
        return png_bytes


def _require_google_credentials() -> None:
    """
    Ensure Google Cloud Vision API credentials are configured.
    Accepts either a file path or inline JSON (the key itself) in GOOGLE_APPLICATION_CREDENTIALS.
    Raises RuntimeError with setup instructions if missing or invalid.
    """
    raw = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or ""
    raw = raw.strip()
    if not raw:
        raise RuntimeError(
            "Google Cloud Vision API requires GOOGLE_APPLICATION_CREDENTIALS to be set. "
            "In the terminal export the key (inline JSON) or a file path: "
            "export GOOGLE_APPLICATION_CREDENTIALS='{\"type\":\"service_account\", ...}'"
        )
    # Inline JSON: value is the key itself (starts with {)
    if raw.startswith("{"):
        try:
            json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"GOOGLE_APPLICATION_CREDENTIALS looks like JSON but is invalid: {e}"
            ) from e
        fd, path = tempfile.mkstemp(suffix=".json", prefix="gcreds_")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(raw)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
        except Exception:
            os.close(fd)
            if os.path.exists(path):
                try:
                    os.unlink(path)
                except Exception:
                    pass
            raise
        return
    # File path
    if not os.path.isfile(raw):
        raise RuntimeError(
            f"GOOGLE_APPLICATION_CREDENTIALS is set to a path that does not exist or is not a file. "
            "Use a file path or export the key JSON directly."
        )


def ensure_google_credentials() -> None:
    """
    Verify Google Cloud Vision API credentials are set and the key file exists.
    Call this at startup or before using Google OCR. Raises RuntimeError if not configured.
    """
    _require_google_credentials()


def get_ocr_provider(name: str = "stub") -> OcrProvider:
    """
    Factory function to get OCR provider by name.
    
    Args:
        name: Provider name ("stub", "google", or "easyocr")
        
    Returns:
        OcrProvider instance
    """
    if name == "stub":
        return StubOcrProvider()
    elif name == "google":
        _require_google_credentials()
        return GoogleVisionOcrProvider()
    elif name == "easyocr":
        return EasyOcrProvider()
    else:
        raise ValueError(f"Unknown OCR provider: {name}")


if __name__ == "__main__":
    import sys
    try:
        ensure_google_credentials()
        path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        print(f"OK: GOOGLE_APPLICATION_CREDENTIALS is set")
        sys.exit(0)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
