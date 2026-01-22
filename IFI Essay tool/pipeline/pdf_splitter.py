"""
PDF multi-entry detection and splitting for batch-scanned submissions.

Handles PDFs containing multiple student entries (typically 2 pages each:
metadata/contact page + essay page) and splits them into separate records.
"""

import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SplitArtifact:
    """Represents a single entry extracted from a multi-entry PDF."""
    group_index: int
    page_start: int  # 0-indexed
    page_end: int    # 0-indexed, inclusive
    output_pdf_path: str
    confidence: float
    signals: Dict[str, Any]


@dataclass
class PDFAnalysis:
    """Analysis results for a PDF document."""
    page_count: int
    pages_text: List[str]  # Extracted text per page
    is_multi_entry: bool
    confidence: float
    detected_groups: List[Tuple[int, int]]  # List of (start_page, end_page) tuples
    signals: Dict[str, Any]


def analyze_pdf_structure(pdf_path: str) -> PDFAnalysis:
    """
    Analyze PDF structure to detect multi-entry documents.
    
    Uses lightweight text extraction (no OCR) to identify:
    - Page count
    - Text patterns suggesting metadata vs essay pages
    - Likely entry boundaries
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        PDFAnalysis with detection results
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("PyMuPDF not installed. Install with: pip install PyMuPDF")
    
    pdf_document = fitz.open(pdf_path)
    page_count = len(pdf_document)
    
    # Extract text from each page (lightweight, no OCR)
    pages_text = []
    for page_num in range(page_count):
        page = pdf_document[page_num]
        text = page.get_text("text")
        pages_text.append(text)
    
    pdf_document.close()
    
    # Detect entry boundaries
    groups, confidence = detect_entry_boundaries(pages_text)
    
    is_multi_entry = len(groups) > 1 and confidence >= 0.7
    
    signals = {
        "page_count": page_count,
        "groups_detected": len(groups),
        "confidence": confidence,
        "detection_method": "text_pattern_analysis"
    }
    
    logger.info(f"PDF analysis: {page_count} pages, {len(groups)} groups detected, confidence={confidence:.2f}")
    
    return PDFAnalysis(
        page_count=page_count,
        pages_text=pages_text,
        is_multi_entry=is_multi_entry,
        confidence=confidence,
        detected_groups=groups,
        signals=signals
    )


def detect_entry_boundaries(pages_text: List[str]) -> Tuple[List[Tuple[int, int]], float]:
    """
    Detect entry boundaries in a multi-entry PDF.
    
    Strategy:
    1. If <= 2 pages: assume single entry
    2. If even pages >= 4: candidate for multi-entry
    3. Classify each page as "metadata-like" or "essay-like"
    4. Group pages into pairs based on pattern consistency
    
    Args:
        pages_text: List of extracted text per page
        
    Returns:
        Tuple of (groups, confidence):
        - groups: List of (start_page, end_page) tuples (0-indexed, inclusive)
        - confidence: 0.0-1.0 score indicating detection certainty
    """
    page_count = len(pages_text)
    
    # Rule 1: Single or two-page PDFs are always single-entry
    if page_count <= 2:
        return [(0, page_count - 1)], 1.0
    
    # Rule 2: Odd page counts are ambiguous (unless 3 pages, which we treat as single-entry)
    if page_count == 3:
        return [(0, 2)], 0.6  # Lower confidence for 3-page PDFs
    
    if page_count % 2 != 0:
        # Odd page count >= 5: uncertain, treat as single-entry
        return [(0, page_count - 1)], 0.4
    
    # Rule 3: Classify each page
    page_types = [_classify_page(text) for text in pages_text]
    
    # Rule 4: Detect pattern (alternating metadata/essay or essay/metadata)
    pattern, pattern_confidence = _detect_page_pattern(page_types)
    
    if pattern is None or pattern_confidence < 0.6:
        # No clear pattern, treat as single-entry
        return [(0, page_count - 1)], pattern_confidence
    
    # Rule 5: Group pages based on detected pattern
    groups = []
    if pattern == "metadata_essay":
        # Pages 0-1, 2-3, 4-5, etc.
        for i in range(0, page_count, 2):
            if i + 1 < page_count:
                groups.append((i, i + 1))
            else:
                # Odd page at end, attach to last group
                if groups:
                    groups[-1] = (groups[-1][0], i)
                else:
                    groups.append((i, i))
    elif pattern == "essay_metadata":
        # Pages 0-1, 2-3, 4-5, etc. (same grouping, different order)
        for i in range(0, page_count, 2):
            if i + 1 < page_count:
                groups.append((i, i + 1))
            else:
                if groups:
                    groups[-1] = (groups[-1][0], i)
                else:
                    groups.append((i, i))
    else:
        # Unknown pattern
        return [(0, page_count - 1)], 0.3
    
    # Confidence is based on pattern consistency
    confidence = pattern_confidence
    
    logger.info(f"Detected {len(groups)} entry groups with pattern '{pattern}', confidence={confidence:.2f}")
    
    return groups, confidence


def _classify_page(text: str) -> str:
    """
    Classify a page as 'metadata', 'essay', or 'unknown'.
    
    Metadata pages have:
    - Short lines
    - Form-like structure
    - Keywords: Name, Grade, School, Phone, Email, etc.
    
    Essay pages have:
    - Longer continuous text blocks
    - Fewer form keywords
    - More narrative content
    
    Args:
        text: Extracted text from page
        
    Returns:
        'metadata', 'essay', or 'unknown'
    """
    if not text or len(text.strip()) < 10:
        return "unknown"
    
    # Metadata indicators
    metadata_keywords = [
        r'\bname\b', r'\bnombre\b', r'\bstudent\b', r'\bestudiante\b',
        r'\bschool\b', r'\bescuela\b', r'\bgrade\b', r'\bgrado\b',
        r'\bteacher\b', r'\bmaestro\b', r'\bphone\b', r'\btel[eé]fono\b',
        r'\bemail\b', r'\bcorreo\b', r'\bfather\b', r'\bpadre\b',
        r'\bfigure\b', r'\bfigura\b'
    ]
    
    # Essay indicators
    essay_keywords = [
        r'\bfather\b', r'\bpadre\b', r'\bfamily\b', r'\bfamilia\b',
        r'\blove\b', r'\bamor\b', r'\bhelp\b', r'\bayuda\b',
        r'\bwork\b', r'\btrabajo\b', r'\bteach\b', r'\bense[ñn]a\b'
    ]
    
    text_lower = text.lower()
    lines = text.split('\n')
    non_empty_lines = [line.strip() for line in lines if line.strip()]
    
    # Count metadata keywords
    metadata_count = sum(1 for keyword in metadata_keywords if re.search(keyword, text_lower, re.IGNORECASE))
    
    # Count essay keywords
    essay_count = sum(1 for keyword in essay_keywords if re.search(keyword, text_lower, re.IGNORECASE))
    
    # Analyze line structure
    avg_line_length = sum(len(line) for line in non_empty_lines) / len(non_empty_lines) if non_empty_lines else 0
    short_lines = sum(1 for line in non_empty_lines if len(line) < 30)
    long_lines = sum(1 for line in non_empty_lines if len(line) > 60)
    
    # Scoring
    metadata_score = 0
    essay_score = 0
    
    # Metadata indicators
    if metadata_count >= 3:
        metadata_score += 3
    elif metadata_count >= 2:
        metadata_score += 2
    elif metadata_count >= 1:
        metadata_score += 1
    
    if short_lines > len(non_empty_lines) * 0.6:
        metadata_score += 2
    
    if avg_line_length < 35:
        metadata_score += 1
    
    # Essay indicators
    if essay_count >= 2:
        essay_score += 2
    
    if long_lines > len(non_empty_lines) * 0.4:
        essay_score += 2
    
    if avg_line_length > 50:
        essay_score += 1
    
    if len(text) > 500:
        essay_score += 1
    
    # Decision
    if metadata_score > essay_score and metadata_score >= 3:
        return "metadata"
    elif essay_score > metadata_score and essay_score >= 2:
        return "essay"
    else:
        return "unknown"


def _detect_page_pattern(page_types: List[str]) -> Tuple[Optional[str], float]:
    """
    Detect if pages follow a consistent pattern.
    
    Looks for:
    - "metadata_essay": metadata on even pages (0, 2, 4...), essay on odd pages (1, 3, 5...)
    - "essay_metadata": essay on even pages, metadata on odd pages
    
    Args:
        page_types: List of page classifications ('metadata', 'essay', 'unknown')
        
    Returns:
        Tuple of (pattern_name, confidence)
        - pattern_name: 'metadata_essay', 'essay_metadata', or None
        - confidence: 0.0-1.0 score
    """
    if len(page_types) < 4:
        return None, 0.0
    
    # Check metadata_essay pattern
    metadata_essay_matches = 0
    metadata_essay_total = 0
    
    for i in range(0, len(page_types), 2):
        if i + 1 < len(page_types):
            metadata_essay_total += 1
            if page_types[i] == "metadata" and page_types[i + 1] == "essay":
                metadata_essay_matches += 1
            elif page_types[i] == "metadata" or page_types[i + 1] == "essay":
                # Partial match
                metadata_essay_matches += 0.5
    
    # Check essay_metadata pattern
    essay_metadata_matches = 0
    essay_metadata_total = 0
    
    for i in range(0, len(page_types), 2):
        if i + 1 < len(page_types):
            essay_metadata_total += 1
            if page_types[i] == "essay" and page_types[i + 1] == "metadata":
                essay_metadata_matches += 1
            elif page_types[i] == "essay" or page_types[i + 1] == "metadata":
                # Partial match
                essay_metadata_matches += 0.5
    
    # Calculate confidence
    metadata_essay_confidence = metadata_essay_matches / metadata_essay_total if metadata_essay_total > 0 else 0.0
    essay_metadata_confidence = essay_metadata_matches / essay_metadata_total if essay_metadata_total > 0 else 0.0
    
    # Choose best pattern
    if metadata_essay_confidence >= 0.6 and metadata_essay_confidence > essay_metadata_confidence:
        return "metadata_essay", metadata_essay_confidence
    elif essay_metadata_confidence >= 0.6:
        return "essay_metadata", essay_metadata_confidence
    else:
        return None, max(metadata_essay_confidence, essay_metadata_confidence)


def split_pdf_into_groups(
    pdf_path: str,
    groups: List[Tuple[int, int]],
    output_dir: str,
    base_filename: str
) -> List[SplitArtifact]:
    """
    Split a PDF into separate files based on detected entry groups.
    
    Args:
        pdf_path: Path to source PDF
        groups: List of (start_page, end_page) tuples (0-indexed, inclusive)
        output_dir: Directory to write split PDFs
        base_filename: Base name for output files (without extension)
        
    Returns:
        List of SplitArtifact objects
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("PyMuPDF not installed. Install with: pip install PyMuPDF")
    
    pdf_document = fitz.open(pdf_path)
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    
    artifacts = []
    
    for group_index, (start_page, end_page) in enumerate(groups):
        # Create new PDF for this group
        output_pdf = fitz.open()
        
        # Copy pages from source PDF
        for page_num in range(start_page, end_page + 1):
            if page_num < len(pdf_document):
                output_pdf.insert_pdf(pdf_document, from_page=page_num, to_page=page_num)
        
        # Save split PDF
        output_filename = f"{base_filename}_entry_{group_index + 1}.pdf"
        output_path = output_dir_path / output_filename
        output_pdf.save(str(output_path))
        output_pdf.close()
        
        # Create artifact
        artifact = SplitArtifact(
            group_index=group_index,
            page_start=start_page,
            page_end=end_page,
            output_pdf_path=str(output_path),
            confidence=1.0,  # Confidence from detection, not splitting
            signals={
                "page_count": end_page - start_page + 1,
                "source_pdf": pdf_path,
                "output_filename": output_filename
            }
        )
        
        artifacts.append(artifact)
        logger.info(f"Created split PDF: {output_filename} (pages {start_page}-{end_page})")
    
    pdf_document.close()
    
    return artifacts


def should_split_pdf(analysis: PDFAnalysis, confidence_threshold: float = 0.7) -> bool:
    """
    Determine if a PDF should be split based on analysis results.
    
    Args:
        analysis: PDFAnalysis result
        confidence_threshold: Minimum confidence to trigger split (default 0.7)
        
    Returns:
        True if PDF should be split, False otherwise
    """
    return analysis.is_multi_entry and analysis.confidence >= confidence_threshold and len(analysis.detected_groups) > 1
