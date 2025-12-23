"""
Extraction module: extracts structured fields from text using rule-based logic.
Handles inconsistent handwriting and optional fields gracefully.
"""

import re
from typing import Optional


def extract_fields_rules(contact_block: str) -> dict:
    """
    Extracts structured contact fields from contact block using pattern matching.
    
    Fields are optional - missing or illegible data returns None.
    Handles variations in handwriting, spacing, and format.
    
    Args:
        contact_block: Text containing contact information
        
    Returns:
        dict with optional fields:
            - student_name
            - school_name
            - grade
            - teacher_name
            - city_or_location
    """
    result = {
        "student_name": None,
        "school_name": None,
        "grade": None,
        "teacher_name": None,
        "city_or_location": None
    }
    
    lines = contact_block.split('\n')
    
    for line in lines:
        line_clean = line.strip()
        line_lower = line_clean.lower()
        
        # Extract name (flexible patterns)
        if 'name:' in line_lower and result["student_name"] is None:
            name_match = re.search(r'name:\s*(.+)', line_clean, re.IGNORECASE)
            if name_match:
                result["student_name"] = name_match.group(1).strip()
        
        # Extract school
        if 'school:' in line_lower and result["school_name"] is None:
            school_match = re.search(r'school:\s*(.+)', line_clean, re.IGNORECASE)
            if school_match:
                result["school_name"] = school_match.group(1).strip()
        
        # Extract grade (numeric)
        if 'grade:' in line_lower and result["grade"] is None:
            grade_match = re.search(r'grade:\s*(\d+)', line_clean, re.IGNORECASE)
            if grade_match:
                try:
                    result["grade"] = int(grade_match.group(1))
                except ValueError:
                    pass
        
        # Extract teacher (optional)
        if 'teacher:' in line_lower and result["teacher_name"] is None:
            teacher_match = re.search(r'teacher:\s*(.+)', line_clean, re.IGNORECASE)
            if teacher_match:
                result["teacher_name"] = teacher_match.group(1).strip()
        
        # Extract location/city (optional)
        if ('city:' in line_lower or 'location:' in line_lower) and result["city_or_location"] is None:
            loc_match = re.search(r'(?:city|location):\s*(.+)', line_clean, re.IGNORECASE)
            if loc_match:
                result["city_or_location"] = loc_match.group(1).strip()
    
    return result


def compute_essay_metrics(essay_block: str) -> dict:
    """
    Computes basic metrics from essay text.
    
    Metrics:
        - word_count: Number of words (whitespace-separated tokens)
        - char_count: Total characters
        - paragraph_count: Number of paragraphs (by double newline)
    
    Args:
        essay_block: Essay text content
        
    Returns:
        dict with computed metrics
    """
    # Word count (simple whitespace split)
    words = essay_block.split()
    word_count = len(words)
    
    # Character count
    char_count = len(essay_block)
    
    # Paragraph count (split by empty lines)
    paragraphs = [p.strip() for p in essay_block.split('\n\n') if p.strip()]
    paragraph_count = len(paragraphs)
    
    return {
        "word_count": word_count,
        "char_count": char_count,
        "paragraph_count": paragraph_count
    }

