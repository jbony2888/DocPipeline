"""
Data models for essay contest submissions.
Uses Pydantic for validation and type safety.
"""

from enum import Enum
from typing import Optional, List, Union, Dict
from pydantic import BaseModel, Field


class DocClass(str, Enum):
    """
    Formal document classification. Every submission has exactly one.
    Classification runs before field extraction.
    """
    SINGLE_TYPED = "SINGLE_TYPED"          # Native PDF text, single page, one submission
    SINGLE_SCANNED = "SINGLE_SCANNED"      # Scanned/image, single page, one submission
    MULTI_PAGE_SINGLE = "MULTI_PAGE_SINGLE"  # One submission spanning multiple pages
    BULK_SCANNED_BATCH = "BULK_SCANNED_BATCH"  # Multiple submissions in one scanned file


class OcrResult(BaseModel):
    """Raw OCR output with confidence metrics."""
    text: str
    confidence_avg: Optional[float] = None
    confidence_min: Optional[float] = None
    confidence_p10: Optional[float] = None
    low_conf_page_count: Optional[int] = None
    lines: List[str] = []
    # When PDF has AcroForm widgets, field_name -> value (e.g. "Student's Name" -> "Test Student Garcia")
    form_field_values: Optional[Dict[str, str]] = None


class SubmissionRecord(BaseModel):
    """
    Complete submission record with extracted fields and metrics.
    Used for validation and CSV export.
    """
    submission_id: str

    # Document classification (assigned before extraction)
    doc_class: DocClass = DocClass.SINGLE_TYPED

    # Contact fields (optional, may be missing or illegible)
    student_name: Optional[str] = None
    school_name: Optional[str] = None
    grade: Optional[Union[int, str]] = None  # Can be integer (1-12) or text ("Kindergarten", "K", etc.)
    teacher_name: Optional[str] = None
    city_or_location: Optional[str] = None
    
    # Additional fields (for bilingual IFI forms)
    father_figure_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    
    # Essay metrics
    word_count: int = 0
    ocr_confidence_avg: Optional[float] = None
    
    # Validation flags
    needs_review: bool = False
    review_reason_codes: str = ""
    
    # Artifact tracking
    artifact_dir: str
