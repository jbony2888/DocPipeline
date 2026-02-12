"""
Data models for essay contest submissions.
Uses Pydantic for validation and type safety.
"""

from typing import Optional, List, Union
from pydantic import BaseModel, Field


class OcrResult(BaseModel):
    """Raw OCR output with confidence metrics."""
    text: str
    confidence_avg: Optional[float] = None
    lines: List[str] = []
    ocr_failed: bool = False  # True if OCR provider raised an error (distinct from low confidence)


class SubmissionRecord(BaseModel):
    """
    Complete submission record with extracted fields and metrics.
    Used for validation and CSV export.
    """
    submission_id: str
    
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

