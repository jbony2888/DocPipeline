"""
OCR provider abstraction with stub and Google Cloud Vision implementations.
"""

import io
import json
import os
import logging
from pathlib import Path
from typing import Protocol
from pipeline.schema import OcrResult

logger = logging.getLogger(__name__)


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
        
        return OcrResult(
            text=simulated_text.strip(),
            confidence_avg=0.65,  # Typical for handwriting
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
                # .env often stores JSON with literal \n between keys; normalize so json.loads() works
                if "\\n" in credentials_json:
                    credentials_json = (
                        credentials_json.replace('{\\n  "', '{\n  "')
                        .replace('",\\n  "', '",\n  "')
                        .replace('"\\n  "', '"\n  "')
                        .replace('"\\n}"', '"\n}"')
                        .replace('"\\n,"', '"\n,"')
                    )
                # Load credentials from JSON string
                try:
                    credentials_dict = json.loads(credentials_json)
                    credentials = service_account.Credentials.from_service_account_info(
                        credentials_dict
                    )
                    self.client = vision.ImageAnnotatorClient(credentials=credentials)
                except json.JSONDecodeError as e:
                    raise RuntimeError(
                        f"Invalid JSON in GOOGLE_CLOUD_VISION_CREDENTIALS_JSON: {e}\n"
                        "Make sure the environment variable contains valid JSON."
                    )
            else:
                # Fall back to standard GOOGLE_APPLICATION_CREDENTIALS (file path)
                # This will use the default credentials chain
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
        
        # Handle PDF files
        try:
            if file_path.suffix.lower() == '.pdf':
                image_bytes = self._render_pdf_to_png(image_path)
            else:
                # Handle image files
                with open(image_path, 'rb') as f:
                    image_bytes = f.read()
        except Exception as e:
            # M5: Safe degradation - if we can't read/render the file, mark as failed
            logger.warning(f"Error reading/rendering file {image_path}: {e}")
            return OcrResult(
                text="",
                confidence_avg=0.0,
                lines=[],
                ocr_failed=True
            )
        
        # Prepare Vision API request
        try:
            image = vision.Image(content=image_bytes)
            
            # Use DOCUMENT_TEXT_DETECTION for handwriting-friendly OCR
            response = self.client.document_text_detection(image=image)
            
            if response.error.message:
                # M5: Safe degradation - return low-confidence result with OCR_FAILED flag
                logger.warning(f"Google Cloud Vision API error: {response.error.message}")
                return OcrResult(
                    text="",
                    confidence_avg=0.0,
                    lines=[],
                    ocr_failed=True  # Mark as failed (distinct from low confidence)
                )
        except Exception as e:
            # M5: Safe degradation - catch any other exceptions during OCR processing
            logger.warning(f"OCR processing error: {e}")
            return OcrResult(
                text="",
                confidence_avg=0.0,
                lines=[],
                ocr_failed=True
            )
        
        # Extract text from response (only reached if no exceptions)
        if response.full_text_annotation and response.full_text_annotation.text:
            extracted_text = response.full_text_annotation.text.strip()
        elif response.text_annotations:
            extracted_text = response.text_annotations[0].description.strip()
        else:
            extracted_text = ""
        
        # Compute quality score (deterministic confidence)
        quality_score = compute_ocr_quality_score(extracted_text)
        
        # Split into lines
        lines = extracted_text.split('\n') if extracted_text else []
        
        return OcrResult(
            text=extracted_text,
            confidence_avg=quality_score,
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
        
        return OcrResult(
            text=extracted_text,
            confidence_avg=final_confidence,
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
        return GoogleVisionOcrProvider()
    elif name == "easyocr":
        return EasyOcrProvider()
    else:
        raise ValueError(f"Unknown OCR provider: {name}")

