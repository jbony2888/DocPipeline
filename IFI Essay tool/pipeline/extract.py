"""
Extraction module: extracts structured fields from text using rule-based logic.
Handles inconsistent handwriting, bilingual forms (English + Spanish), 
and multi-line form layouts gracefully.
"""

import re
import unicodedata
from pathlib import Path
from typing import Optional, Union


# Bilingual label aliases (English + Spanish).
# Standard IFI form (e.g. 2025 IFI Fatherhood Essay Contest) uses clear labels that make
# extraction reliable: value is on same line after ":" or on the next line.
STUDENT_NAME_ALIASES = [
    "student's name", "student name", "students name", "student name:", "student's name:",
    "student's name / nombre del estudiante", "nombre del estudiante",
    "name", "student:",
    "estudiante", "nombre", "nombre:", "estudiante:"
]

SCHOOL_ALIASES = [
    "school", "school name", "school:",
    "school / escuela", "escuela", "escuela:", "nombre de la escuela"
]

GRADE_ALIASES = [
    "grade", "grade level", "grade:",
    "grade / grado", "grado", "grado:"
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
    - Normalizing Unicode apostrophes/quotes to ASCII (so "Student's" matches)
    - Converting to lowercase
    - Removing accents (á → a, ñ → n)
    - Collapsing whitespace

    Fixes #6: PDFs often use Unicode RIGHT SINGLE QUOTATION MARK (') instead of
    ASCII apostrophe ('), so "Student's Name" in docs would not match aliases.
    """
    if not text:
        return ""
    # Normalize Unicode apostrophes/quotes to ASCII so label matching works
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
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

    # Proper-noun style values (e.g. "De La Salle Institute") should not be
    # rejected as labels just because they contain stopwords like "de"/"la".
    raw_words = [w for w in re.split(r"\s+", line.strip()) if w]
    alpha_words = [w for w in raw_words if re.fullmatch(r"[A-Za-z'\-]+", w)]
    if 2 <= len(alpha_words) <= 8:
        non_label_alpha = [w for w in alpha_words if normalize_text(w) not in LABEL_KEYWORDS]
        if non_label_alpha and any(len(w) >= 4 for w in non_label_alpha):
            return False
    
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


# Essay/sentence starters that indicate captured text is essay body, not a form field value
_ESSAY_FRAGMENT_STARTERS = (
    "and ", "at ", "if ", "the ", "to ", "she ", "he ", "my ", "because ", "when ", "that ",
    "so ", "but ", "or ", "in ", "on ", "for ", "with ", "is ", "was ", "has ", "have ",
    "it ", "we ", "they ", "this ", "what ", "and if ", "of ", "as ", "by ", "from ",
    "a ", "a father to ", "a father to",  # e.g. "a father to Adrian" from father reaction
    "fatherhood essay ", "fatherhood essay",  # essay title, not student name
    "friend ", "friend",  # e.g. "Friend Hes My Dad Patient" from essay body, not school
)

# Sentence starters / essay fragments to reject as student name (reduce false positives)
_STUDENT_NAME_REJECT_WORDS = frozenset({"porque", "estar", "yo", "mi", "se"})
_WEEKDAY_WORDS = frozenset(
    {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
)
_MONTH_WORDS = frozenset(
    {
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    }
)


def looks_like_essay_fragment(text: str) -> bool:
    """
    Return True if text looks like essay/sentence content rather than a form value (e.g. school name).
    Used to reject captures that are essay text after a label on the same line.
    """
    if not text or not text.strip():
        return False
    low = text.strip().lower()
    return any(low.startswith(s) for s in _ESSAY_FRAGMENT_STARTERS)


def is_plausible_student_name(value: str, max_line_length: int = 40) -> bool:
    """
    Structural checks so we don't accept essay fragments as student name.
    Position (top 20%, within 3 lines of anchor) is enforced by callers; here we check shape.

    - 2–4 tokens (words)
    - At least one token capitalized (or title-case)
    - Reject common sentence starters: porque, estar, yo, mi, se
    - Reject lines > max_line_length (default 40)
    """
    if not value or not value.strip():
        return False
    s = re.sub(r"^[^A-Za-z]+", "", value.strip())
    s = s.strip()
    if not s:
        return False
    if len(s) > max_line_length:
        return False
    if re.search(r"\d", s):
        return False
    lower = normalize_text(s)
    if "page" in lower and re.search(r"\bpage\s+\d+\b", lower):
        return False
    if any(day in lower for day in _WEEKDAY_WORDS) and any(month in lower for month in _MONTH_WORDS):
        return False
    if any(day in lower for day in _WEEKDAY_WORDS) and "," in s:
        return False
    tokens = s.split()
    if not (2 <= len(tokens) <= 4):
        return False
    low_tokens = [t.lower() for t in tokens if t]
    if any(t in _STUDENT_NAME_REJECT_WORDS for t in low_tokens):
        return False
    # At least one token should look like a name (starts with uppercase or is title-case)
    # Allow all-lowercase names from forms (e.g. "yojan carranza") - treat as valid if 2-4 alpha words
    if not any(t and t[0].isupper() for t in tokens):
        if all(t and t.isalpha() for t in tokens) and 2 <= len(tokens) <= 4:
            return True  # Form may have name in lowercase
        return False
    return True


def student_name_from_filename(filename: str | None) -> Optional[str]:
    """
    Try to get a plausible student name from filename when form field is empty.
    E.g. "Santiago Flores - 26-IFI-Essay-Form-Eng-and-Spanish.pdf" -> "Santiago Flores".
    Used as fallback for IFI typed forms when Student's Name field is empty.
    """
    if not filename or not filename.strip():
        return None
    stem = Path(filename).stem
    # Reject template-only filenames (no student name): "26-IFI-Essay-Form-Eng-and-Spanish (2).pdf"
    stem_norm = re.sub(r"[\s()]", "", stem).lower()
    if stem_norm.startswith("26-ifi-essay-form") or stem_norm.startswith("26-if-essay-form"):
        return None
    parts = re.split(r"[-_\s]+", stem)
    name_parts = []
    for p in parts:
        # Allow apostrophes in names (e.g. Ta'kerah, O'Brien)
        p_alpha = re.sub(r"['\u2019\u2018]", "", p)
        if not p or not p_alpha.isalpha():
            continue
        if len(p_alpha) < 2 or len(p_alpha) > 25:
            continue
        low = p.lower()
        if low in ("ifi", "essay", "contest", "fatherhood", "form", "export", "pdf", "the", "and", "eng", "spanish"):
            continue
        name_parts.append(p)
        if len(name_parts) >= 3:
            break
    if len(name_parts) < 2:
        return None
    candidate = " ".join(name_parts)
    if not is_plausible_student_name(candidate, max_line_length=40):
        return None
    return candidate


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
    max_length: int = 60,
    same_line_only: bool = False,
    value_after_label_only: bool = False,
) -> Optional[str]:
    """
    Find a line containing any label alias and extract the associated value.
    
    Tries multiple strategies:
    1. Value after ':' on same line
    2. Value after alias text on same line
    3. Value on previous 1-2 lines (if same_line_only and value_after_label_only are False)
    4. Value on next 1-2 lines (if same_line_only is False)
    
    When same_line_only is True (e.g. typed forms), only strategies 1-2 are used.
    When value_after_label_only is True (e.g. scanned forms), only use text that comes
    AFTER the label: same line or next line(s). Never use text above the label.
    
    Args:
        lines: List of text lines
        label_aliases: List of label variations to search for
        start_index: Index to start searching from
        max_length: Maximum length for value
        same_line_only: If True, only extract value from the same line as the label
        value_after_label_only: If True, only use value on same line or next line(s); skip previous lines
        
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
                    # Guard: when extracting student_name, never treat Father/Father-Figure label
                    # text itself as the value (e.g. \"Father's-Figure Name\").
                    val_norm = normalize_text(value)
                    if any(
                        kw in val_norm
                        for kw in (
                            "father", "father-", "padre", "figura paterna", "grandfather",
                            "stepdad", "abuelo"
                        )
                    ):
                        value = None
                    if value:
                        return value
                
                # Strategy 2: Value after alias on same line (no colon)
                # Handle patterns like:
                # - "Student: Nombre del Estudiante Andrick Vargas-Hernandezade / Grado"
                # - "Student's Name Jordan Altman"
                # - "Nombre del Estudiante: Maria Garcia"
                import re
                
                # Try to find the alias (case-insensitive)
                alias_pattern = re.compile(re.escape(alias), re.IGNORECASE)
                match = alias_pattern.search(line)
                
                if match:
                    # Extract text after the alias match
                    start_pos = match.end()
                    original_after = line[start_pos:].strip()
                    
                    # Remove common separators and additional labels
                    # Handle cases like "Nombre del Estudiante Andrick..." where we need to skip the Spanish label
                    original_after = original_after.lstrip(':/-').strip()
                    
                    # If there's another label after the first one (e.g., "Nombre del Estudiante" after "Student:"),
                    # skip it and get what comes after
                    for other_alias in label_aliases:
                        if other_alias != alias:
                            other_alias_pattern = re.compile(re.escape(other_alias), re.IGNORECASE)
                            other_match = other_alias_pattern.search(original_after)
                            if other_match:
                                # Skip the second label and get what's after it
                                original_after = original_after[other_match.end():].strip()
                                original_after = original_after.lstrip(':/-').strip()
                                break
                    
                    # Remove trailing separators like "/ Grado" or "/ Grade"
                    # Split by "/" and take the first part (the name)
                    if '/' in original_after:
                        parts = original_after.split('/')
                        original_after = parts[0].strip()
                    
                    # Remove common trailing words that aren't part of the name
                    # Remove words like "Grado", "Grade", etc.
                    trailing_words = ['grado', 'grade', 'escuela', 'school']
                    words = original_after.split()
                    filtered_words = []
                    for word in words:
                        word_lower = word.lower().rstrip('.,:;')
                        if word_lower not in trailing_words:
                            filtered_words.append(word)
                        else:
                            break  # Stop at first trailing word
                    original_after = ' '.join(filtered_words).strip()

                    if original_after and is_valid_value_candidate(original_after, max_length):
                        # Guard: for student_name extraction, do not return values that
                        # are clearly the Father/Father-Figure label text.
                        val_norm = normalize_text(original_after)
                        if any(
                            kw in val_norm
                            for kw in (
                                "father", "father-", "padre", "figura paterna", "grandfather",
                                "stepdad", "abuelo"
                            )
                        ):
                            original_after = ""
                        if original_after:
                            return original_after
                
                # Fallback: Remove the alias from normalized line and check if value remains
                line_after_alias = line_norm.replace(alias_norm, '', 1).strip()
                line_after_alias = line_after_alias.lstrip(':/-').strip()
                if line_after_alias and is_valid_value_candidate(line_after_alias, max_length):
                    # Try to find the original case version by searching for alias variants
                    for alias_variant in label_aliases:
                        alias_variant_norm = normalize_text(alias_variant)
                        if alias_variant_norm in line_norm:
                            # Find position in normalized line
                            norm_idx = line_norm.find(alias_variant_norm)
                            if norm_idx >= 0:
                                # Try to find corresponding position in original line
                                # This is approximate but works for most cases
                                # Find where the alias ends in the original line
                                # by looking for the alias text (case-insensitive)
                                variant_pattern = re.compile(re.escape(alias_variant), re.IGNORECASE)
                                variant_match = variant_pattern.search(line)
                                if variant_match:
                                    original_after = line[variant_match.end():].strip()
                                    original_after = original_after.lstrip(':/-').strip()
                                    if original_after and is_valid_value_candidate(original_after, max_length):
                                        val_norm = normalize_text(original_after)
                                        if any(
                                            kw in val_norm
                                            for kw in (
                                                "father", "father-", "padre", "figura paterna",
                                                "grandfather", "stepdad", "abuelo"
                                            )
                                        ):
                                            original_after = ""
                                        if original_after:
                                            return original_after
                    # Last resort: return normalized version (will be lowercase but better than nothing)
                    val_norm = line_after_alias
                    if any(
                        kw in val_norm
                        for kw in (
                            "father", "father-", "padre", "figura paterna", "grandfather",
                            "stepdad", "abuelo"
                        )
                    ):
                        return None
                    return val_norm
                
                if same_line_only:
                    # Typed-form layout: value is only on same line as label; do not use next/previous lines
                    return None
                
                # Strategy 3: Check previous 1-2 lines (only when not value_after_label_only)
                # For scans we only target text that comes AFTER the label.
                if not value_after_label_only:
                    for j in range(1, 3):
                        if i - j >= start_index:
                            prev_line = lines[i - j].strip()
                            if prev_line and is_valid_value_candidate(prev_line, max_length):
                                if not is_likely_label_line(prev_line):
                                    return prev_line
                
                # Strategy 4: Check next 1-2 lines for value (text after the label)
                for j in range(1, 3):
                    if i + j < len(lines):
                        next_line = lines[i + j].strip()
                        if not next_line or not is_valid_value_candidate(next_line, max_length):
                            continue
                        # Don't use a line that is itself another label (e.g. "Father/Father-Figure Name")
                        if is_likely_label_line(next_line):
                            continue
                        return next_line
                
                # Found label but no value - return None for this search
                return None
    
    return None


# Reject years and out-of-range: grade valid only as single token 1-12 or K near anchor
_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
# Single token: only 1-12, K, or ordinal (5th, 3rd). No years, no two-digit > 12.
_SINGLE_GRADE_DIGIT = re.compile(r"^([1-9]|1[0-2])$")
_SINGLE_GRADE_ORDINAL = re.compile(r"^([1-9]|1[0-2])(?:st|nd|rd|th)$", re.IGNORECASE)


def parse_grade(text: Optional[str]) -> Optional[Union[int, str]]:
    """
    Parse grade from text. Valid only when:
    - Near anchor label ("Grade", "Grado") – caller must restrict to label-proximate text.
    - Single numeric token 1–12, or K.
    - Not part of a sentence (no years, no two-digit > 12).

    Rejects: years (2022, 2023), two-digit > 12, numbers embedded in paragraphs.
    Returns None when not confidently a grade.

    Formats supported:
    - "8", "2", "12" -> integer
    - "Grade 5", "Grado 3", "Grade: 5", "Grade: 5th" -> integer
    - "5th", "3rd" (single token or with grade/grado) -> integer
    - "K", "Kinder", "Kindergarten" -> "K"
    """
    if not text:
        return None

    text = text.strip()
    if not text:
        return None

    text_upper = text.upper()
    tokens = text.split()

    # Reject years (e.g. 2022, 2023) anywhere in text
    if _YEAR_PATTERN.search(text):
        return None

    # Reject any two-digit number > 12 (e.g. 22, 99)
    two_digit = re.findall(r"\b(\d{2})\b", text)
    for num_str in two_digit:
        n = int(num_str)
        if n > 12:
            return None

    # Reject 4-digit numbers (years) as single token
    if len(tokens) == 1 and re.match(r"^\d{4}$", tokens[0]):
        return None

    # Kindergarten: accept as single token or short phrase with K/kinder.
    # Include common OCR misspellings seen in scanned submissions (e.g. Kindergarden, Kindergartesi,
    # and initial-letter confusion like "Rinder"/"Prinder").
    kindergarten_variants = ("K", "KINDER", "KINDERGARTEN", "PRE-K", "PRE-KINDERGARTEN")
    kindergarten_ocr_pattern = re.compile(
        r"\b(?:pre[\s\-]?k|kinder(?:garten|garden)?|kinder(?:garte)?n|"
        r"[prk]inder(?:garten|garden)?|kindergard(?:en|an)|kindergar(?:den|dan)|kindergart(?:en|esi))\b",
        re.IGNORECASE,
    )
    if text_upper in kindergarten_variants or (
        len(tokens) <= 2 and any(v in text_upper for v in kindergarten_variants)
    ):
        return "K"
    if len(tokens) <= 4 and kindergarten_ocr_pattern.search(text):
        return "K"

    # Single numeric token 1–12 only (digit or ordinal)
    if len(tokens) == 1:
        tok = tokens[0]
        if _SINGLE_GRADE_DIGIT.match(tok):
            return int(tok)
        ordinal = _SINGLE_GRADE_ORDINAL.match(tok)
        if ordinal:
            return int(ordinal.group(1))
        if tok.upper() in kindergarten_variants:
            return "K"
        return None

    # Multi-token: accept only anchor-adjacent patterns (Grade/Grado followed by 1–12 or ordinal)
    if len(tokens) > 4:
        return None  # Likely sentence, not label value
    # Grade/Grado : 5 or 5th
    grade_grado = re.search(
        r"(?:grade|grado)\s*[:\-/]?\s*([1-9]|1[0-2])(?:st|nd|rd|th)?\b", text, re.IGNORECASE
    )
    if grade_grado:
        return int(grade_grado.group(1))
    # 5 or 5th after Grade/Grado (same line)
    num_after = re.search(
        r"\b([1-9]|1[0-2])(?:st|nd|rd|th)?\s*(?:grade|grado)\b", text, re.IGNORECASE
    )
    if num_after:
        return int(num_after.group(1))

    return None


def find_grade_fallback(lines: list[str]) -> Optional[Union[int, str]]:
    """
    Fallback grade search only near "Grade" or "Grado" anchor.
    Does not scan the full block to avoid essay-number contamination
    (e.g. years, numbers in paragraphs).

    Only considers lines within a few lines of a Grade/Grado label.
    Returns None when no grade is confidently found near anchor.
    """
    for i, line in enumerate(lines):
        line_norm = normalize_text(line)
        if "grade" not in line_norm and "grado" not in line_norm:
            continue
        # Search only within 3 lines before and 3 lines after the anchor
        search_start = max(0, i - 3)
        search_end = min(len(lines), i + 4)
        for j in range(search_start, search_end):
            check_line = lines[j].strip()
            # Prefer standalone single token 1-12 on its own line
            if re.match(r"^([1-9]|1[0-2])$", check_line):
                grade = parse_grade(check_line)
                if grade is not None:
                    return grade
            # Same line as label: "Grade 5" or "Grade: 5"
            grade = parse_grade(check_line)
            if grade is not None:
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
    
    # Extract student name (scans: only use text that comes after the label)
    student_name = extract_value_near_label(
        lines, STUDENT_NAME_ALIASES, value_after_label_only=True
    )
    debug["matches"]["student_name"] = {
        "aliases_searched": STUDENT_NAME_ALIASES,
        "value_found": student_name,
        "matched": student_name is not None
    }
    
    # Extract school (scans: only use text that comes after the label)
    school_name = extract_value_near_label(
        lines, SCHOOL_ALIASES, value_after_label_only=True
    )
    debug["matches"]["school_name"] = {
        "aliases_searched": SCHOOL_ALIASES,
        "value_found": school_name,
        "matched": school_name is not None
    }
    
    # Extract grade (scans: only use text that comes after the label)
    grade_text = extract_value_near_label(
        lines, GRADE_ALIASES, max_length=30, value_after_label_only=True
    )
    grade = parse_grade(grade_text)

    # Fallback: only near Grade/Grado anchor (no full-block scan, no essay-body numbers)
    if grade is None:
        grade = find_grade_fallback(lines)
        debug["matches"]["grade"] = {
            "aliases_searched": GRADE_ALIASES,
            "grade_text_found": grade_text,
            "parsed_grade": grade,
            "matched": grade is not None,
            "method": "fallback_near_anchor"
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
    
    # Extract father figure name (optional, for IFI form; value after label only)
    father_figure_name = extract_value_near_label(
        lines, FATHER_FIGURE_ALIASES, max_length=80, value_after_label_only=True
    )
    debug["matches"]["father_figure_name"] = {
        "aliases_searched": FATHER_FIGURE_ALIASES[:3],  # Show first 3
        "value_found": father_figure_name,
        "matched": father_figure_name is not None
    }
    
    # Extract phone (optional; value after label only)
    phone = extract_value_near_label(
        lines, PHONE_ALIASES, max_length=30, value_after_label_only=True
    )
    debug["matches"]["phone"] = {
        "aliases_searched": PHONE_ALIASES,
        "value_found": phone,
        "matched": phone is not None
    }
    
    # Extract email (optional; value after label only)
    email = extract_value_near_label(
        lines, EMAIL_ALIASES, max_length=80, value_after_label_only=True
    )
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
