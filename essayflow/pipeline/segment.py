"""
Segmentation module: separates contact info from essay body.
Uses heuristics to handle inconsistent handwritten layouts.
"""

import re


def split_contact_vs_essay(raw_text: str) -> tuple[str, str]:
    """
    Splits OCR text into contact block and essay block.
    
    Strategy:
    - Contact info is typically at the top, compact, and contains
      anchor words like "Name:", "School:", "Grade:", "Teacher:"
    - Essay body is the dominant free-form text below
    - Split after first substantial paragraph break or around line 10
    
    Args:
        raw_text: Full OCR text output
        
    Returns:
        Tuple of (contact_block, essay_block)
    """
    lines = raw_text.strip().split('\n')
    
    # Heuristic: contact section is usually first 3-10 lines
    # Look for the transition point
    contact_end_idx = 3  # minimum lines for contact
    
    # Anchor words that suggest contact section
    contact_keywords = ['name:', 'school:', 'grade:', 'teacher:', 'location:', 'city:']
    
    for idx, line in enumerate(lines[:15]):  # Check first 15 lines max
        line_lower = line.lower().strip()
        
        # If we see contact keywords, likely still in contact section
        if any(keyword in line_lower for keyword in contact_keywords):
            contact_end_idx = max(contact_end_idx, idx + 1)
        
        # If we hit a long paragraph line after seeing contact info, that's the essay start
        if idx > 2 and len(line.strip()) > 50 and not any(keyword in line_lower for keyword in contact_keywords):
            break
    
    # Look for first empty line after contact section (typical layout break)
    for idx in range(contact_end_idx, min(len(lines), 12)):
        if not lines[idx].strip():
            contact_end_idx = idx
            break
    
    # Split at the transition point
    contact_lines = lines[:contact_end_idx]
    essay_lines = lines[contact_end_idx:]
    
    contact_block = '\n'.join(contact_lines).strip()
    essay_block = '\n'.join(essay_lines).strip()
    
    return contact_block, essay_block

