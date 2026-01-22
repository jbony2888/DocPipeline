"""
Multi-Entry PDF Detection and Splitting

Detects PDFs with multiple student entries and splits them into individual PDFs.
"""

import fitz  # PyMuPDF
import re
from pathlib import Path
from typing import List, Tuple, Optional
from pydantic import BaseModel


class PageAnalysis(BaseModel):
    """Analysis of a single PDF page."""
    page_num: int
    text_preview: str
    text_length: int
    has_metadata_labels: bool
    has_essay_content: bool
    metadata_score: float  # 0.0 to 1.0


class MultiEntryDetection(BaseModel):
    """Result of multi-entry PDF detection."""
    is_multi_entry: bool
    confidence: float
    entry_boundaries: List[Tuple[int, int]]  # (start_page, end_page) for each entry
    total_entries: int
    pattern: str  # "metadata+essay", "single", "unknown"


def analyze_page(page: fitz.Page, page_num: int) -> PageAnalysis:
    """
    Analyze a single PDF page to determine if it's metadata or essay content.
    
    Metadata pages typically have:
    - Labels like "Student Name:", "School:", "Grade:", etc.
    - Short text
    - Form-like structure
    
    Essay pages typically have:
    - Longer text (200+ words)
    - Paragraphs
    - Less structured format
    """
    text = page.get_text()
    text_lower = text.lower()
    
    # Metadata indicators
    metadata_labels = [
        r'student\s*name',
        r'school',
        r'grade',
        r'teacher',
        r'email',
        r'phone',
        r'father\s*figure',
        r'entry\s*form',
    ]
    
    label_count = sum(1 for pattern in metadata_labels if re.search(pattern, text_lower))
    word_count = len(text.split())
    
    # Scoring
    has_metadata_labels = label_count >= 2  # At least 2 metadata labels
    has_essay_content = word_count > 100  # Substantial text
    
    # Metadata score: higher = more likely metadata page
    metadata_score = 0.0
    if label_count > 0:
        metadata_score += min(label_count / 5.0, 0.6)  # Max 0.6 for labels
    if word_count < 150:
        metadata_score += 0.3  # Short text suggests metadata
    if word_count > 200:
        metadata_score -= 0.4  # Long text suggests essay
    
    metadata_score = max(0.0, min(1.0, metadata_score))
    
    return PageAnalysis(
        page_num=page_num,
        text_preview=text[:200],
        text_length=len(text),
        has_metadata_labels=has_metadata_labels,
        has_essay_content=has_essay_content,
        metadata_score=metadata_score
    )


def detect_multi_entry(pdf_path: str, pages_per_entry: int = 2) -> MultiEntryDetection:
    """
    Detect if a PDF contains multiple student entries.
    
    For scanned PDFs (common for handwritten essays):
    - Assumes each entry has a fixed number of pages (default: 2)
    - Page 1: Metadata form
    - Page 2: Essay
    
    Args:
        pdf_path: Path to PDF file
        pages_per_entry: Number of pages per student entry (default: 2)
    
    Pattern detection:
    - If page_count is divisible by pages_per_entry and > pages_per_entry, 
      it's likely multi-entry
    - Otherwise, single entry
    """
    doc = fitz.open(pdf_path)
    page_count = doc.page_count
    
    if page_count < pages_per_entry:
        doc.close()
        return MultiEntryDetection(
            is_multi_entry=False,
            confidence=1.0,
            entry_boundaries=[(0, page_count - 1)],
            total_entries=1,
            pattern="single"
        )
    
    # Check if pages are scanned (no extractable text)
    first_page = doc[0]
    first_page_text = first_page.get_text().strip()
    is_scanned = len(first_page_text) == 0
    
    if is_scanned:
        print(f"📄 Scanned PDF detected (no extractable text)")
        
        # For scanned PDFs, use page count heuristic
        if page_count % pages_per_entry == 0 and page_count > pages_per_entry:
            # Likely multi-entry
            total_entries = page_count // pages_per_entry
            entry_boundaries = [
                (i * pages_per_entry, (i + 1) * pages_per_entry - 1)
                for i in range(total_entries)
            ]
            
            doc.close()
            return MultiEntryDetection(
                is_multi_entry=True,
                confidence=0.8,  # Moderate confidence (based on page count only)
                entry_boundaries=entry_boundaries,
                total_entries=total_entries,
                pattern=f"{pages_per_entry}-pages-per-entry"
            )
        else:
            # Odd page count or single entry
            doc.close()
            return MultiEntryDetection(
                is_multi_entry=False,
                confidence=0.9,
                entry_boundaries=[(0, page_count - 1)],
                total_entries=1,
                pattern="single"
            )
    
    # For text-based PDFs, use original text analysis logic
    if page_count < 2:
        doc.close()
        return MultiEntryDetection(
            is_multi_entry=False,
            confidence=1.0,
            entry_boundaries=[(0, page_count - 1)],
            total_entries=1,
            pattern="single"
        )
    
    # Analyze all pages
    pages = []
    for i in range(page_count):
        page = doc[i]
        analysis = analyze_page(page, i)
        pages.append(analysis)
    
    doc.close()
    
    # Detect pattern: metadata page followed by essay page
    entry_boundaries = []
    i = 0
    
    while i < len(pages):
        # Look for metadata page
        if pages[i].metadata_score > 0.5:  # Likely metadata page
            start_page = i
            
            # Next page should be essay (if pattern holds)
            if i + 1 < len(pages) and pages[i + 1].metadata_score < 0.5:
                end_page = i + 1
                entry_boundaries.append((start_page, end_page))
                i += 2  # Skip both pages
            else:
                # Single page entry or irregular pattern
                entry_boundaries.append((start_page, start_page))
                i += 1
        else:
            # If we haven't detected any entries yet and we're past page 0,
            # treat as single-entry PDF
            if len(entry_boundaries) == 0 and i > 0:
                entry_boundaries = [(0, page_count - 1)]
                break
            i += 1
    
    # Determine if multi-entry
    total_entries = len(entry_boundaries)
    is_multi_entry = total_entries > 1
    
    # Confidence based on pattern consistency
    confidence = 0.5
    if total_entries == 1:
        confidence = 0.9  # High confidence for single entry
    elif total_entries > 1:
        # Check pattern consistency
        page_counts = [end - start + 1 for start, end in entry_boundaries]
        if len(set(page_counts)) == 1:  # All entries have same page count
            confidence = 0.9
        else:
            confidence = 0.7
    
    pattern = "metadata+essay" if is_multi_entry else "single"
    
    return MultiEntryDetection(
        is_multi_entry=is_multi_entry,
        confidence=confidence,
        entry_boundaries=entry_boundaries if entry_boundaries else [(0, page_count - 1)],
        total_entries=total_entries if total_entries > 0 else 1,
        pattern=pattern
    )


def split_pdf(pdf_path: str, entry_boundaries: List[Tuple[int, int]], output_dir: str) -> List[str]:
    """
    Split a multi-entry PDF into individual entry PDFs.
    
    Args:
        pdf_path: Path to the source PDF
        entry_boundaries: List of (start_page, end_page) tuples
        output_dir: Directory to save split PDFs
        
    Returns:
        List of paths to the created PDF files
    """
    import os
    
    doc = fitz.open(pdf_path)
    output_paths = []
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    original_name = Path(pdf_path).stem
    
    for idx, (start_page, end_page) in enumerate(entry_boundaries, start=1):
        # Create new PDF with pages from this entry
        new_doc = fitz.open()
        
        for page_num in range(start_page, end_page + 1):
            if page_num < doc.page_count:
                new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
        
        # Save split PDF
        output_filename = f"{original_name}_entry_{idx}.pdf"
        output_path = os.path.join(output_dir, output_filename)
        new_doc.save(output_path)
        new_doc.close()
        
        output_paths.append(output_path)
        print(f"Created: {output_filename} (pages {start_page}-{end_page})")
    
    doc.close()
    return output_paths
