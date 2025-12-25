"""
Extraction module: extracts structured fields from text using rule-based logic.
Handles inconsistent handwriting, bilingual forms (English + Spanish), 
and multi-line form layouts gracefully.
"""

import re
import unicodedata
from typing import Optional


# Bilingual label aliases (English + Spanish)
STUDENT_NAME_ALIASES = [
    "student's name", "student name", "students name", "name",
    "nombre del estudiante", "estudiante", "nombre"
]

SCHOOL_ALIASES = [
    "school", "school name",
    "escuela"
]

GRADE_ALIASES = [
    "grade", "grade level",
    "grado"
]

FATHER_FIGURE_ALIASES = [
    "father", "father's name", "father name", "father-figure", "father figure",
    "padre", "nombre del padre", "figura paterna", "father-figure name",
    "fatherlfather-figure name"  # OCR might merge labels
]

PHONE_ALIASES = [
    "phone", "telephone", "phone number",
    "telefono", "teléfono"
]

EMAIL_ALIASES = [
    "email", "e-mail", "email address",
    "correo", "correo electronico", "correo electrónico"
]

# Known label words to skip when looking for values on next lines
LABEL_KEYWORDS = {
    "name", "nombre", "school", "escuela", "grade", "grado", "teacher", "maestro",
    "phone", "telefono", "teléfono", "email", "correo", "deadline", "initiative",
    "contest", "concurso", "writing", "escribiendo", "father", "padre", "figure",
    "figura", "about", "sobre", "maximum", "maximo", "máximo", "character", "caracteres",
    "reaction", "reaccion", "reacción", "student's", "del", "de", "la", "el"
}


def normalize_text(text: str) -> str:
    """
    Normalize text for matching by:
    - Converting to lowercase
    - Removing accents (á → a, ñ → n)
    - Collapsing whitespace
    
    Args:
        text: Input text
        
    Returns:
        Normalized text
    """
    # Convert to lowercase
    text = text.lower()
    
    # Remove accents (NFD decomposition, then filter out combining marks)
    text = unicodedata.normalize('NFD', text)
    text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')
    
    # Collapse whitespace
    text = ' '.join(text.split())
    
    return text


def is_likely_label_line(line: str) -> bool:
    """
    Check if line looks like a label-only line (no actual value).
    
    Args:
        line: Text line
        
    Returns:
        True if line appears to be just a label
    """
    norm = normalize_text(line)
    
    # Empty or very short
    if len(norm) < 2:
        return True
    
    # Contains common label keywords
    words = norm.split()
    if any(word in LABEL_KEYWORDS for word in words):
        # If it's mostly label words and punctuation, it's probably just a label
        non_label_words = [w for w in words if w not in LABEL_KEYWORDS and w not in ':/']
        if len(non_label_words) <= 1:
            return True
    
    # Contains "deadline", "character maximum", "contest" (form text, not values)
    if any(keyword in norm for keyword in ['deadline', 'maximum', 'contest', 'initiative']):
        return True
    
    return False


def is_valid_value_candidate(text: str, max_length: int = 60, min_alpha_ratio: float = 0.4) -> bool:
    """
    Check if text looks like a valid field value.
    
    Args:
        text: Candidate value text
        max_length: Maximum acceptable length
        min_alpha_ratio: Minimum ratio of alphanumeric characters
        
    Returns:
        True if text could be a valid value
    """
    text = text.strip()
    
    # Empty
    if not text:
        return False
    
    # Single character usually not a value (unless it's a grade check elsewhere)
    if len(text) == 1 and not text.isdigit():
        return False
    
    # Too long (probably not a name/school/grade)
    if len(text) > max_length:
        return False
    
    # Mostly punctuation or special chars (OCR noise)
    alnum_chars = sum(1 for c in text if c.isalnum())
    if len(text) > 0 and alnum_chars < len(text) * min_alpha_ratio:
        return False
    
    # Looks like a label line
    if is_likely_label_line(text):
        return False
    
    return True


def extract_value_after_colon(line: str) -> Optional[str]:
    """
    Extract value after a colon in the same line.
    
    Args:
        line: Text line
        
    Returns:
        Value after colon, or None
    """
    if ':' in line:
        parts = line.split(':', 1)
        if len(parts) == 2:
            value = parts[1].strip()
            if is_valid_value_candidate(value):
                return value
    return None


def extract_value_near_label(
    lines: list[str],
    label_aliases: list[str],
    start_index: int = 0,
    max_length: int = 60
) -> Optional[str]:
    """
    Find a line containing any label alias and extract the associated value.
    
    Tries multiple strategies:
    1. Value after ':' on same line
    2. Value after alias text on same line
    3. Value on next 1-2 lines (if they're not labels themselves)
    
    Args:
        lines: List of text lines
        label_aliases: List of label variations to search for
        start_index: Index to start searching from
        max_length: Maximum length for value
        
    Returns:
        Extracted value or None
    """
    for i in range(start_index, len(lines)):
        line = lines[i].strip()
        line_norm = normalize_text(line)
        
        # Check if this line contains any of our label aliases
        for alias in label_aliases:
            alias_norm = normalize_text(alias)
            if alias_norm in line_norm:
                # Strategy 1: Value after colon on same line
                value = extract_value_after_colon(line)
                if value:
                    return value
                
                # Strategy 2: Value after alias on same line (no colon)
                # Remove the alias and see if there's a value left
                line_after_alias = line_norm.replace(alias_norm, '', 1).strip()
                line_after_alias = line_after_alias.lstrip(':/-').strip()
                if line_after_alias and is_valid_value_candidate(line_after_alias, max_length):
                    # Find the corresponding text in original line (preserves case)
                    # This is approximate but good enough
                    original_after = line.split(alias, 1)[-1].strip()
                    original_after = original_after.lstrip(':/-').strip()
                    if original_after and is_valid_value_candidate(original_after, max_length):
                        return original_after
                
                # Strategy 3: Check previous 1-2 lines for value (form may have value above label)
                for j in range(1, 3):
                    if i - j >= start_index:
                        prev_line = lines[i - j].strip()
                        if prev_line and is_valid_value_candidate(prev_line, max_length):
                            # Make sure this isn't another label
                            if not is_likely_label_line(prev_line):
                                return prev_line
                
                # Strategy 4: Check next 1-2 lines for value
                for j in range(1, 3):
                    if i + j < len(lines):
                        next_line = lines[i + j].strip()
                        if next_line and is_valid_value_candidate(next_line, max_length):
                            return next_line
                
                # Found label but no value - return None for this search
                return None
    
    return None


def parse_grade(text: Optional[str]) -> Optional[int]:
    """
    Parse grade from text, handling various formats.
    
    Formats supported:
    - "8", "2"
    - "2nd", "3rd", "4th"
    - "2nd grade", "grado 2"
    - OCR noise like "Grade / Grado 8"
    
    Args:
        text: Text potentially containing grade
        
    Returns:
        Grade as integer (1-12), or None
    """
    if not text:
        return None
    
    text = text.strip()
    
    # Extract first 1-2 digit number
    numbers = re.findall(r'\b(\d{1,2})\b', text)
    for num_str in numbers:
        try:
            grade = int(num_str)
            # Validate grade range
            if 1 <= grade <= 12:
                return grade
        except ValueError:
            continue
    
    return None


def find_grade_fallback(lines: list[str]) -> Optional[int]:
    """
    Fallback grade search - look for standalone digit in contact block.
    Searches near grade labels first, then scans entire contact block.
    
    Args:
        lines: List of text lines
        
    Returns:
        Grade as integer, or None
    """
    # First pass: Look within 5 lines of "Grade" or "Grado" labels
    for i, line in enumerate(lines):
        line_norm = normalize_text(line)
        if 'grade' in line_norm or 'grado' in line_norm:
            # Check 5 lines before and after
            search_start = max(0, i - 5)
            search_end = min(len(lines), i + 6)
            for j in range(search_start, search_end):
                check_line = lines[j].strip()
                # Look for single digit or two-digit number on its own line
                if re.match(r'^\d{1,2}$', check_line):
                    grade = parse_grade(check_line)
                    if grade:
                        return grade
    
    # Second pass: Look for any standalone digit in entire contact block
    for line in lines:
        line_stripped = line.strip()
        
        # Skip lines that are obviously not grades
        if is_likely_label_line(line):
            continue
        
        # Look for lines that are JUST a number (1-2 digits)
        if re.match(r'^\d{1,2}$', line_stripped):
            grade = parse_grade(line_stripped)
            if grade:
                return grade
    
    # Third pass: Look for grade in any line
    for line in lines:
        if is_likely_label_line(line):
            continue
        
        grade = parse_grade(line)
        if grade:
            return grade
    
    return None


def extract_fields_rules(contact_block: str, return_debug: bool = False) -> dict:
    """
    Extracts structured contact fields from contact block using bilingual pattern matching.
    
    Handles:
    - English and Spanish labels
    - Multi-line form layouts (label on one line, value on next)
    - Value after colon or on same line as label
    - Various grade formats (2, 2nd, grado 2)
    
    Fields are optional - missing or illegible data returns None.
    Handles variations in handwriting, spacing, and format.
    
    Args:
        contact_block: Text containing contact information
        return_debug: If True, returns (result, debug_info) tuple
        
    Returns:
        dict with optional fields (or tuple if return_debug=True):
            - student_name
            - school_name
            - grade
            - teacher_name
            - city_or_location
            - father_figure_name (optional)
            - phone (optional)
            - email (optional)
    """
    lines = [line.strip() for line in contact_block.split('\n') if line.strip()]
    
    # Debug tracking
    debug = {
        "total_lines": len(lines),
        "contact_block_preview": lines[:10] if len(lines) > 10 else lines,
        "matches": {},
        "candidates": {},
        "extraction_method": "rule-based"
    }
    
    # Extract student name
    student_name = extract_value_near_label(lines, STUDENT_NAME_ALIASES)
    debug["matches"]["student_name"] = {
        "aliases_searched": STUDENT_NAME_ALIASES,
        "value_found": student_name,
        "matched": student_name is not None
    }
    
    # Extract school
    school_name = extract_value_near_label(lines, SCHOOL_ALIASES)
    debug["matches"]["school_name"] = {
        "aliases_searched": SCHOOL_ALIASES,
        "value_found": school_name,
        "matched": school_name is not None
    }
    
    # Extract grade
    grade_text = extract_value_near_label(lines, GRADE_ALIASES, max_length=30)
    grade = parse_grade(grade_text)
    
    # Fallback: scan for standalone grade number if not found
    if grade is None:
        grade = find_grade_fallback(lines)
        debug["matches"]["grade"] = {
            "aliases_searched": GRADE_ALIASES,
            "grade_text_found": grade_text,
            "parsed_grade": grade,
            "matched": grade is not None,
            "method": "fallback_scan"
        }
    else:
        debug["matches"]["grade"] = {
            "aliases_searched": GRADE_ALIASES,
            "grade_text_found": grade_text,
            "parsed_grade": grade,
            "matched": True,
            "method": "near_label"
        }
    
    # Extract teacher (original logic preserved for English forms)
    teacher_name = None
    for line in lines:
        line_lower = normalize_text(line)
        if 'teacher' in line_lower or 'maestro' in line_lower:
            value = extract_value_after_colon(line)
            if value:
                teacher_name = value
                break
    
    # Extract city/location (original logic preserved)
    city_or_location = None
    for line in lines:
        line_lower = normalize_text(line)
        if 'city' in line_lower or 'location' in line_lower or 'ciudad' in line_lower:
            value = extract_value_after_colon(line)
            if value:
                city_or_location = value
                break
    
    # Extract father figure name (optional, for IFI form)
    father_figure_name = extract_value_near_label(lines, FATHER_FIGURE_ALIASES, max_length=80)
    debug["matches"]["father_figure_name"] = {
        "aliases_searched": FATHER_FIGURE_ALIASES[:3],  # Show first 3
        "value_found": father_figure_name,
        "matched": father_figure_name is not None
    }
    
    # Extract phone (optional)
    phone = extract_value_near_label(lines, PHONE_ALIASES, max_length=30)
    debug["matches"]["phone"] = {
        "aliases_searched": PHONE_ALIASES,
        "value_found": phone,
        "matched": phone is not None
    }
    
    # Extract email (optional)
    email = extract_value_near_label(lines, EMAIL_ALIASES, max_length=80)
    debug["matches"]["email"] = {
        "aliases_searched": EMAIL_ALIASES[:3],  # Show first 3
        "value_found": email,
        "matched": email is not None
    }
    
    result = {
        "student_name": student_name,
        "school_name": school_name,
        "grade": grade,
        "teacher_name": teacher_name,
        "city_or_location": city_or_location,
        "father_figure_name": father_figure_name,
        "phone": phone,
        "email": email
    }
    
    # Summary
    debug["summary"] = {
        "fields_extracted": sum(1 for v in result.values() if v is not None),
        "required_fields_found": {
            "student_name": student_name is not None,
            "school_name": school_name is not None,
            "grade": grade is not None
        }
    }
    
    if return_debug:
        return result, debug
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

