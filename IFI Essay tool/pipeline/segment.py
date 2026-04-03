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


_REACTION_ANCHORS = [
    'father/grandfather/step-dad/father-figure reaction',
    'reaction to this essay',
    'reaccion de padre/abuelo',
]

_FOOTER_LINE_PATTERNS = [
    'barrington, il',
    'grove avenue',
    '4dads.org',
    'ifi will also',
    'ifi will cite',
    'positive essay/response',
    'publications and media',
    'contest is open to illinois',
    'deadline for upload or postmark',
    'criteria for essay judging',
    'character maximum',
    'maximo de caracteres',
    'figura paterna puede ser',
    'ideal vision of a father',
    'completed forms can be uploaded',
    'parent/guardian permission',
    'submissions will be evaluated',
    'judging criteria will consist',
    'una figura paterna puede ser',
    'reverse side',
    'confidentiality if requested',
    'conceal names to maintain',
    'world-wide basis',
    'world wide basis',
    'non-exclusive, royalty-free',
    'royalty-free',
    'how the essay describes',
    'honesty, clarity, simplici',
    'detail and stories that demonstrate',
]

_INLINE_ANCHORS = [
    'God, or an ideal vision of a father',
    'RULES able to return them',
    'CRITERIA FOR ESSAY JUDGING',
]


def strip_footer_boilerplate(essay_text: str) -> str:
    """Remove IFI contest rules / form boilerplate that appears after the student essay."""
    if not essay_text or not essay_text.strip():
        return essay_text

    lines = essay_text.split('\n')

    # Primary anchor: "reaction to this essay" is extremely specific to the
    # IFI form and always marks the boundary between the student's essay and
    # the parent-reaction / rules section.  Search bottom-up so the *last*
    # occurrence wins (handles forms that print the prompt twice).
    cut_idx = None
    for i in range(len(lines) - 1, -1, -1):
        line_norm = normalize_for_matching(lines[i].strip())
        if any(anchor in line_norm for anchor in _REACTION_ANCHORS):
            cut_idx = i
            break

    if cut_idx is not None:
        # Scan upward past consecutive anchor lines (English + Spanish pair).
        while cut_idx > 0:
            prev_norm = normalize_for_matching(lines[cut_idx - 1].strip())
            if any(anchor in prev_norm for anchor in _REACTION_ANCHORS):
                cut_idx -= 1
            else:
                break
        lines = lines[:cut_idx]

    # Secondary: peel off trailing boilerplate lines one at a time.
    while lines:
        last = lines[-1].strip()
        if not last:
            lines.pop()
            continue
        last_norm = normalize_for_matching(last)
        if any(pat in last_norm for pat in _FOOTER_LINE_PATTERNS):
            lines.pop()
        elif len(last) <= 3 and not last[0].isalpha():
            lines.pop()
        else:
            break

    # Inline contamination on the final surviving line (single-line OCR noise).
    if lines:
        last_line = lines[-1]
        for anchor in _INLINE_ANCHORS:
            pos = last_line.find(anchor)
            if pos > 0:
                lines[-1] = last_line[:pos].rstrip()
                break

    return '\n'.join(lines).strip()


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
    
    # Keywords that reliably indicate form labels regardless of line length
    contact_keywords_strict = [
        'student', 'estudiante',
        'school', 'escuela',
        'grade', 'grado',
        'teacher', 'maestro',
        'phone', 'telefono', 'teléfono',
        'email', 'correo',
        'location', 'ciudad',
        'deadline',
    ]

    # Keywords that appear in both form labels AND essay content (e.g. "father",
    # "about", "writing").  Only treat these as contact-block markers on short
    # lines that look like form labels, not on long essay paragraphs.
    contact_keywords_ambiguous = [
        'name', 'nombre',
        'father', 'padre', 'figure', 'figura',
        'writing', 'escribiendo',
        'about', 'sobre', 'contest', 'concurso',
        'city',
    ]

    LABEL_LINE_MAX_LENGTH = 80
    
    # Markers that suggest the essay is starting or essay prompt area
    essay_start_markers = [
        'character maximum', 'maximo de caracteres', 'máximo de caracteres',
        'reaction to this essay', 'reaccion', 'reacción',
        'what my father', 'what my dad', 'lo que mi padre',
        'father means to me', 'padre significa para mi',
    ]

    # Markers that indicate the PROMPT section (after this, essay content follows)
    essay_prompt_markers = [
        'father / padre',
        'grandfather',
        'stepdad',
        'father-figure / figura paterna',
        'father / grandfather',
        'figura paterna',
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
        
        # Check if line contains contact keywords.
        # Strict keywords match on any line; ambiguous keywords only on short label-like lines.
        contains_contact_keyword = any(keyword in line_norm for keyword in contact_keywords_strict)
        if not contains_contact_keyword and len(line_stripped) <= LABEL_LINE_MAX_LENGTH:
            contains_contact_keyword = any(keyword in line_norm for keyword in contact_keywords_ambiguous)
        
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
    
    # Ensure we don't cut off too early; relax from 10 to 6 for forms with few header lines
    contact_end_idx = max(contact_end_idx, 6)
    
    # Split at the transition point
    contact_lines = lines[:contact_end_idx]
    essay_lines = lines[contact_end_idx:]
    
    contact_block = '\n'.join(contact_lines).strip()
    essay_block = '\n'.join(essay_lines).strip()

    essay_block = strip_footer_boilerplate(essay_block)
    
    return contact_block, essay_block

