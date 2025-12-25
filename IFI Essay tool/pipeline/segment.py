"""
Segmentation module: separates contact info from essay body.
Uses heuristics to handle inconsistent handwritten layouts, including bilingual forms.
"""

import re
import unicodedata


def normalize_for_matching(text: str) -> str:
    """Normalize text for keyword matching (lowercase, remove accents)."""
    text = text.lower()
    text = unicodedata.normalize('NFD', text)
    text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')
    return text


def split_contact_vs_essay(raw_text: str) -> tuple[str, str]:
    """
    Splits OCR text into contact block and essay block.
    
    Strategy for bilingual/form-based layouts:
    - Contact section includes all form fields (may span 30+ lines)
    - Look for both English and Spanish field labels
    - Essay starts after "character maximum" or when we see long handwritten paragraphs
    - Forms may have labels without colons, on separate lines from values
    
    Args:
        raw_text: Full OCR text output
        
    Returns:
        Tuple of (contact_block, essay_block)
    """
    lines = raw_text.strip().split('\n')
    
    if len(lines) <= 3:
        # Very short text, return as-is
        return raw_text, ""
    
    # Anchor words that suggest contact/form section (bilingual, with or without colons)
    contact_keywords = [
        'name', 'nombre', 'student', 'estudiante',
        'school', 'escuela',
        'grade', 'grado',
        'teacher', 'maestro',
        'phone', 'telefono', 'teléfono',
        'email', 'correo',
        'father', 'padre', 'figure', 'figura',
        'location', 'ciudad', 'city',
        'deadline', 'writing', 'escribiendo',
        'about', 'sobre', 'contest', 'concurso'
    ]
    
    # Markers that suggest the essay is starting or essay prompt area
    essay_start_markers = [
        'character maximum', 'maximo de caracteres', 'máximo de caracteres',
        'reaction to this essay', 'reaccion', 'reacción'
    ]
    
    # Markers that indicate the PROMPT section (after this, essay content follows)
    essay_prompt_markers = [
        'father / padre',
        'grandfather',
        'stepdad',
        'father-figure / figura paterna'
    ]
    
    # Strategy: Find where form ends and essay begins
    contact_end_idx = 3  # minimum
    essay_likely_started = False
    seen_essay_prompt_section = False
    consecutive_long_lines = 0
    
    for idx, line in enumerate(lines[:50]):  # Check first 50 lines (forms can be long)
        line_stripped = line.strip()
        line_norm = normalize_for_matching(line_stripped)
        
        # Empty lines don't tell us much
        if not line_stripped:
            consecutive_long_lines = 0
            continue
        
        # Check if we hit essay prompt markers (checkboxes like "Father / Padre", etc.)
        if any(marker in line_norm for marker in essay_prompt_markers):
            seen_essay_prompt_section = True
            contact_end_idx = max(contact_end_idx, idx + 1)
            consecutive_long_lines = 0
            continue
        
        # Check if we hit an essay start marker
        if any(marker in line_norm for marker in essay_start_markers):
            # This line is still part of the form (it's a label)
            contact_end_idx = max(contact_end_idx, idx + 1)
            essay_likely_started = True
            consecutive_long_lines = 0
            continue
        
        # Check if line contains contact keywords
        contains_contact_keyword = any(keyword in line_norm for keyword in contact_keywords)
        
        # After seeing essay prompt section, long lines without contact keywords are essay
        if seen_essay_prompt_section and not contains_contact_keyword and len(line_stripped) > 30:
            # This is likely the essay starting
            contact_end_idx = idx
            break
        
        if contains_contact_keyword:
            # Still in contact section
            contact_end_idx = max(contact_end_idx, idx + 1)
            consecutive_long_lines = 0
        else:
            # Line doesn't have contact keywords
            # Check if it's a long handwritten paragraph (likely essay)
            if len(line_stripped) > 40:
                consecutive_long_lines += 1
                
                # If we've seen the essay start marker AND now have long text, essay is starting
                if essay_likely_started and consecutive_long_lines >= 2:
                    # Essay starts a few lines back
                    contact_end_idx = max(contact_end_idx, idx - 1)
                    break
                
                # Or if we're past line 30 and seeing lots of long lines, essay likely started
                if idx > 30 and consecutive_long_lines >= 3:
                    contact_end_idx = idx - 2
                    break
            else:
                # Short line without keywords - might be a value, keep it in contact
                consecutive_long_lines = 0
                contact_end_idx = max(contact_end_idx, idx + 1)
    
    # Ensure we don't cut off too early
    contact_end_idx = max(contact_end_idx, 10)
    
    # Split at the transition point
    contact_lines = lines[:contact_end_idx]
    essay_lines = lines[contact_end_idx:]
    
    contact_block = '\n'.join(contact_lines).strip()
    essay_block = '\n'.join(essay_lines).strip()
    
    return contact_block, essay_block

