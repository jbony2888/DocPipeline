"""
Two-phase extraction for IFI Fatherhood Essay Contest submissions.

Phase 1: Classify document type
Phase 2: Extract structured data based on document type
"""

import os
import json
import re
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


_LLM_RUNTIME_STATE = {
    "disabled": False,
    "failure_reason": None,
    "disabled_logged": False,
    "no_key_warned": False,
}


def _disable_llm_runtime(reason: str) -> None:
    """Disable LLM calls for this process after a hard runtime failure."""
    _LLM_RUNTIME_STATE["disabled"] = True
    _LLM_RUNTIME_STATE["failure_reason"] = reason


def _reset_llm_runtime_state_for_tests() -> None:
    """Test helper to reset module runtime flags."""
    _LLM_RUNTIME_STATE["disabled"] = False
    _LLM_RUNTIME_STATE["failure_reason"] = None
    _LLM_RUNTIME_STATE["disabled_logged"] = False
    _LLM_RUNTIME_STATE["no_key_warned"] = False


def extract_ifi_submission(
    raw_ocr_text: str,
    contact_block: str = None,
    essay_block: str = None,
    original_filename: str = None
) -> Dict[str, Any]:
    """
    Two-phase extraction for IFI essay submissions.
    
    Phase 1: Classify document type
    Phase 2: Extract fields based on classification
    
    Args:
        raw_ocr_text: Full OCR text
        contact_block: Contact section (if already segmented)
        essay_block: Essay section (if already segmented)
        original_filename: Original filename for fallback
        
    Returns:
        Dictionary with classification, extraction, and metadata
    """
    # Groq is used for normalization (OpenAI is not used)
    groq_key = os.environ.get("GROQ_API_KEY")

    if not groq_key:
        if not _LLM_RUNTIME_STATE["no_key_warned"]:
            logger.warning("GROQ_API_KEY not set - falling back to rule-based extraction")
            _LLM_RUNTIME_STATE["no_key_warned"] = True
        return _extract_ifi_fallback(
            raw_ocr_text,
            original_filename,
            fallback_reason="no_groq_api_key",
        )

    if _LLM_RUNTIME_STATE["disabled"]:
        if not _LLM_RUNTIME_STATE["disabled_logged"]:
            logger.warning(
                "IFI LLM extraction disabled for this process after prior failure: %s. "
                "Using fallback extraction.",
                _LLM_RUNTIME_STATE.get("failure_reason") or "unknown",
            )
            _LLM_RUNTIME_STATE["disabled_logged"] = True
        return _extract_ifi_fallback(
            raw_ocr_text,
            original_filename,
            fallback_reason=f"llm_runtime_disabled:{_LLM_RUNTIME_STATE.get('failure_reason') or 'unknown'}",
        )
    
    try:
        # Groq for normalization (schema-aligned extraction from OCR text)
        from groq import Groq
        client = Groq(api_key=groq_key)
        model_name = "llama-3.3-70b-versatile"
        provider = "groq"

        # Build comprehensive prompt
        prompt = _build_ifi_extraction_prompt(raw_ocr_text, original_filename)
        
        # Call LLM (Groq) to normalize OCR text to schema
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You normalize OCR text from scanned documents into structured fields per the SubmissionRecord schema. Return only valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content
        result = json.loads(result_text)
        
        # Add metadata
        result['extraction_method'] = 'llm_ifi'
        result['model'] = f"{model_name} ({provider})"
        
        # Normalize grade format
        if result.get('grade'):
            result['grade'] = _normalize_grade(result['grade'])
        
        logger.info(f"IFI extraction complete: doc_type={result.get('doc_type')}, "
                   f"student={result.get('student_name')}, grade={result.get('grade')}")
        
        return result
    
    except Exception as e:
        reason = f"{type(e).__name__}: {e}"
        _disable_llm_runtime(reason)
        logger.warning("IFI LLM extraction failed, switching to fallback mode: %s", reason)
        return _extract_ifi_fallback(
            raw_ocr_text,
            original_filename,
            fallback_reason=f"llm_error:{reason}",
        )


def _build_ifi_extraction_prompt(ocr_text: str, filename: str = None) -> str:
    """Build the comprehensive two-phase extraction prompt."""
    
    prompt = f"""You are extracting structured data from IFI Fatherhood Essay Contest submissions.

OCR TEXT:
```
{ocr_text}
```

FILENAME: {filename if filename else "unknown"}

TASK: Classify the document, then extract fields. Return JSON only.

===== PHASE 1: CLASSIFICATION =====

Classify as ONE of these doc_types:

1. IFI_OFFICIAL_FORM_FILLED
   - Contains labeled form fields: "Student's Name / Nombre del Estudiante", "Grade / Grado", "School/Escuela"
   - Has essay prompt text: "What my father or an important father-figure means to me"
   - Contains checkbox options: "Father / Padre", "Grandfather/Abuelo", "Stepdad / Padrasto"
   - Has HANDWRITTEN values filled in
   - May include parent reaction section

2. IFI_OFFICIAL_TEMPLATE_BLANK
   - Has all the form structure from #1
   - But NO handwritten student values (only labels and instructions)
   - Essentially a blank Kami export or template

3. ESSAY_WITH_HEADER_METADATA
   - First 1-4 lines contain student info WITHOUT labels
   - Format usually: Name, School, Grade on separate lines or inline
   - Example: "John Smith / Lincoln Elementary / 3rd Grade"
   - Then essay body follows

4. ESSAY_ONLY
   - Pure essay text with NO metadata
   - No name, school, or grade present
   - Just the essay content

5. MULTI_ENTRY
   - Contains MORE than one student's submission in a single document
   - Multiple names, multiple essays, or page breaks between submissions

Also determine:
- is_blank_template: true if document is a blank form with no student data
- language: "English" | "Spanish" | "Mixed" based on essay content

===== PHASE 2: EXTRACTION =====

REQUIRED SCHEMA FIELDS (SubmissionRecord - extract these when present; use null only if absent):
- student_name: REQUIRED for record approval - extract from labels or header
- school_name: REQUIRED for record approval - extract from School/Escuela or header
- grade: REQUIRED for record approval - integer 1-12 or "K", extract from Grade/Grado or header

Extract these fields (DO NOT GUESS - only extract if explicitly present or reasonably inferred from OCR):

student_name (string | null):
- From "Student's Name / Nombre del Estudiante" label (official forms)
- From first line (header metadata format)
- Look for names near labels like "Name:", "Student:", "Estudiante:"
- Common patterns: "Name: Jordan Altman", "Student's Name: Maria Garcia"
- Names are typically 2-4 words (first + last name, sometimes middle)
- Correct OCR errors (e.g., "Alv4rez" -> "Alvarez", "J0rdan" -> "Jordan")
- If you see a name that looks like a person's name (capitalized words, 2-4 words), extract it
- DO NOT extract from filename - only from PDF document content
- null ONLY if absolutely no name is visible in the document

school_name (string | null):
- From "School / Escuela" label proximity
- From header lines containing "School", "Elementary", "Middle", "High"
- null if not found

grade (integer 1-12 OR "K" | null):
- From "Grade / Grado" label
- From ordinal text: "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th", "11th", "12th"
- From words: "Kinder", "Kindergarten", "K" -> "K"
- From "Grade 5" or "5th Grade" format
- Return as integer for 1-12, or string "K" for kindergarten
- null if not found

father_figure_name (string | null):
- From "Father/Father-Figure Name / Nombre del Padre" label
- Real person's name (e.g., "John Smith")
- NOT state names (Illinois, Texas), NOT "Fatherhood", NOT "Father"
- null if not found

father_figure_type ("Father" | "Grandfather" | "Stepdad" | "Father-Figure" | null):
- From checkbox selection in form
- From essay context if explicitly stated
- null if unclear

essay_text (string | null):
- For official forms: text between prompt and parent reaction section
- For essay-only: entire document body
- For header metadata: lines after the header
- Remove form labels and instructions
- null if blank template or missing

parent_reaction_text (string | null):
- Text under "Father/Grandfather/Step-Dad/Father-Figure reaction to this essay"
- Or "Reacción de padre/abuelo/padrastro/figura paterna"
- null if not present

topic ("Father" | "Mother" | "Other"):
- "Father" if essay is about father/father-figure (default/expected)
- "Mother" if essay primarily focuses on mother/mom
- "Other" if about another person

is_off_prompt (boolean):
- true if topic != "Father" (essay doesn't follow prompt)
- false if essay is about father/father-figure

notes (array of strings):
- Explain any ambiguity
- Note if data is inferred vs. explicitly present
- Flag OCR errors that were corrected
- Note if template is blank

===== EXTRACTION RULES BY DOC_TYPE =====

IFI_OFFICIAL_TEMPLATE_BLANK:
- is_blank_template = true
- All extraction fields = null
- notes = ["Blank template detected - no student data present"]

IFI_OFFICIAL_FORM_FILLED:
- Use bilingual label proximity
- Look for values near labels (before or after)
- Essay is between prompt and reaction section
- Parent reaction is separate block

ESSAY_WITH_HEADER_METADATA:
- Parse first 1-4 lines for name/school/grade
- Essay starts after metadata
- No form labels present

ESSAY_ONLY:
- Only extract essay_text
- All metadata fields = null
- notes = ["Essay-only document - no metadata present"]

MULTI_ENTRY:
- Extract first student only
- notes = ["Multi-entry document - extracted first entry only"]

===== OUTPUT FORMAT =====

Return JSON with this exact structure:
{{
  "doc_type": "IFI_OFFICIAL_FORM_FILLED",
  "is_blank_template": false,
  "language": "Spanish",
  "student_name": "Maria Garcia",
  "school_name": "Lincoln Elementary",
  "grade": 3,
  "father_figure_name": "Carlos Garcia",
  "father_figure_type": "Father",
  "essay_text": "Mi papa significa...",
  "parent_reaction_text": "Me da mucha alegria...",
  "topic": "Father",
  "is_off_prompt": false,
  "notes": ["OCR corrected: Garcla -> Garcia"]
}}

CRITICAL RULES:
- REQUIRED schema fields (student_name, school_name, grade): extract when present; null only if absent
- DO NOT hallucinate missing values - use null when not found
- DO NOT invent or fabricate student_name or school_name - only output values that appear explicitly in the document; use null if not clearly present
- If unsure, prefer null over guessing
- Correct obvious OCR errors (l->I, 0->O, etc.)
- For blank templates, set ALL extraction fields to null
- DO NOT extract student_name from filename - only from PDF document content
- Grade must be 1-12 (int) or "K" (string) or null
- Essay text should NOT include form labels or instructions

Generate the JSON now:"""
    
    return prompt


def _normalize_grade(grade_value: Any) -> Optional[Any]:
    """
    Normalize grade to integer (1-12) or string "K".
    
    Args:
        grade_value: Raw grade value from LLM
        
    Returns:
        Normalized grade (int 1-12, string "K", or None)
    """
    if grade_value is None:
        return None
    
    # Already normalized
    if isinstance(grade_value, int) and 1 <= grade_value <= 12:
        return grade_value
    
    if isinstance(grade_value, str):
        grade_str = grade_value.strip().upper()
        
        # Kindergarten
        if grade_str in ['K', 'KINDER', 'KINDERGARTEN']:
            return 'K'
        
        # Ordinal numbers
        ordinal_map = {
            '1ST': 1, '2ND': 2, '3RD': 3, '4TH': 4, '5TH': 5,
            '6TH': 6, '7TH': 7, '8TH': 8, '9TH': 9, '10TH': 10,
            '11TH': 11, '12TH': 12
        }
        
        if grade_str in ordinal_map:
            return ordinal_map[grade_str]
        
        # Extract digits; reject years (4-digit) and two-digit > 12
        digits = re.search(r'\d+', grade_str)
        if digits:
            grade_int = int(digits.group())
            if len(digits.group()) >= 4:
                return None  # years (2022, 1999)
            if grade_int > 12:
                return None
            if 1 <= grade_int <= 12:
                return grade_int

    return None


def _extract_freeform_name_school_grade(text: str) -> Dict[str, Any]:
    """
    Extract student name, school, and grade from freeform layout:
    - Line 1: Student name (no label), e.g. "David Coronel"
    - Line 2: School name + grade, e.g. "Rachel Carson School 6th grade"

    Scans first and last N lines of the document (name/school often at top or bottom).
    Returns dict with student_name, school_name, grade (or empty dict if not found).
    """
    if not text or not text.strip():
        return {}
    from pipeline.extract import is_plausible_student_name, is_valid_value_candidate
    from pipeline.normalize import sanitize_grade

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if len(lines) < 2:
        return {}

    # Match "School Name Nth grade" or "School Name N grade" (e.g. "Rachel Carson School 6th grade")
    school_grade_re = re.compile(
        r"^(.+?)\s+(\d{1,2})(?:st|nd|rd|th)?\s*grade\s*$",
        re.IGNORECASE,
    )
    result = {}

    def scan_region(line_list: List[str]) -> bool:
        for i in range(1, len(line_list)):
            school_grade_match = school_grade_re.match(line_list[i])
            if not school_grade_match:
                continue
            school_part = school_grade_match.group(1).strip()
            grade_num = int(school_grade_match.group(2))
            if grade_num < 1 or grade_num > 12:
                continue
            prev_line = line_list[i - 1].strip()
            if not prev_line or len(prev_line) > 40:
                continue
            if not is_plausible_student_name(prev_line, max_line_length=40):
                continue
            low = prev_line.lower()
            if low in ("student's name", "student name", "nombre del estudiante", "school", "grade"):
                continue
            if is_valid_value_candidate(school_part, max_length=120):
                result["student_name"] = prev_line
                result["school_name"] = school_part
                result["grade"] = sanitize_grade(grade_num)
                return True
        return False

    n_zone = 12
    if scan_region(lines[:n_zone]):
        return result
    if len(lines) > n_zone and scan_region(lines[-n_zone:]):
        return result
    return {}


# Typed freeform: header-only zone for Groq (fewer lines = better extraction)
FREEFORM_HEADER_LINES = 25
FREEFORM_HEADER_CHARS = 2500


def _get_freeform_header_text(contact_block: str, raw_text: str) -> str:
    """Return the top portion of the document where name/school/grade usually appear."""
    text = (contact_block or "") + "\n" + (raw_text or "")
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if not lines:
        return ""
    header_lines = lines[:FREEFORM_HEADER_LINES]
    header_text = "\n".join(header_lines)
    if len(header_text) > FREEFORM_HEADER_CHARS:
        header_text = header_text[:FREEFORM_HEADER_CHARS]
    return header_text


def _build_freeform_normalize_prompt(header_text: str, heuristic_result: Dict[str, Any]) -> str:
    """Build prompt for Groq to normalize heuristic extractions and fill missing from header."""
    sn = heuristic_result.get("student_name") or "null"
    school = heuristic_result.get("school_name") or "null"
    grade = heuristic_result.get("grade") if heuristic_result.get("grade") is not None else "null"
    return f"""We have preliminary extractions from the TOP of a student essay (from rule-based heuristics):

CURRENT EXTRACTIONS:
- student_name: {sn}
- school_name: {school}
- grade: {grade}

HEADER TEXT (first part of document only):
```
{header_text}
```

TASK: Normalize and complete these fields.
1. Normalize: clean spelling, fix obvious OCR errors, standardize grade (integer 1-12 or "K").
2. Fill missing: if a field is null but clearly present in the header text above, extract it (e.g. first line = name, second line = school).
3. Do NOT invent: only use values explicitly in the header. Use null for any field not clearly present.

Return valid JSON only:
{{
  "student_name": "Normalized Name or null",
  "school_name": "Normalized School or null",
  "grade": 6
}}"""


def _normalize_freeform_metadata_via_groq(
    header_text: str, heuristic_result: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Groq normalizes heuristic extractions: clean values and fill missing from header.
    Returns dict with student_name, school_name, grade or None on failure.
    Does not disable the main LLM on failure.
    """
    if not header_text or not header_text.strip():
        return None
    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        return None
    if _LLM_RUNTIME_STATE["disabled"]:
        return None
    try:
        from groq import Groq

        client = Groq(api_key=groq_key)
        model_name = "llama-3.3-70b-versatile"
        prompt = _build_freeform_normalize_prompt(header_text, heuristic_result)
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You normalize and complete student metadata from header text. Return only valid JSON with keys student_name, school_name, grade. Do not invent values."
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        result_text = response.choices[0].message.content
        result = json.loads(result_text)
        out = {
            "student_name": result.get("student_name") or None,
            "school_name": result.get("school_name") or None,
            "grade": None,
        }
        if result.get("grade") is not None:
            out["grade"] = _normalize_grade(result["grade"])
        logger.info(
            "Typed freeform Groq normalize: student=%s, school=%s, grade=%s",
            out.get("student_name"),
            out.get("school_name"),
            out.get("grade"),
        )
        return out
    except Exception as e:
        logger.warning("Typed freeform Groq normalize failed (using heuristics only): %s", e)
        return None


def _extract_freeform_heuristics(contact_block: str, raw_text: str) -> Dict[str, Any]:
    """
    Heuristics-first extraction for freeform typed essays.
    Student name, school, and grade are at the top; no form labels.

    Runs in order: (1) freeform "Name" + "School Nth grade" pattern,
    (2) label proximity on contact/header lines, (3) grade by placement.
    Returns dict with student_name, school_name, grade (None when not found).
    """
    text = (contact_block or "") + "\n" + (raw_text or "")
    result = {"student_name": None, "school_name": None, "grade": None}

    # 1. Freeform pattern (top then bottom of doc)
    freeform = _extract_freeform_name_school_grade(text)
    for k in ("student_name", "school_name", "grade"):
        if freeform.get(k) is not None:
            result[k] = freeform[k]

    # 2. Label-based extraction from contact/header (first 15 lines = top)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    top_lines = lines[:15] if len(lines) >= 15 else lines
    if top_lines:
        from pipeline.extract import (
            extract_value_near_label,
            find_grade_fallback,
            parse_grade,
            is_valid_value_candidate,
            looks_like_essay_fragment,
            is_plausible_student_name,
            STUDENT_NAME_ALIASES,
            SCHOOL_ALIASES,
            GRADE_ALIASES,
        )
        from pipeline.normalize import sanitize_grade

        if result.get("student_name") is None:
            sn = extract_value_near_label(top_lines, STUDENT_NAME_ALIASES, max_length=40)
            if sn:
                low = sn.lower()
                if low not in ("student's name", "student name", "nombre del estudiante"):
                    if is_plausible_student_name(sn, max_line_length=40):
                        result["student_name"] = sn
        if result.get("school_name") is None:
            school = extract_value_near_label(top_lines, SCHOOL_ALIASES, max_length=120)
            if school and is_valid_value_candidate(school, max_length=120) and not looks_like_essay_fragment(school):
                result["school_name"] = school
        if result.get("grade") is None:
            grade_text = extract_value_near_label(top_lines, GRADE_ALIASES, max_length=30)
            g = parse_grade(grade_text) if grade_text else find_grade_fallback(top_lines)
            if g is not None:
                result["grade"] = sanitize_grade(g)

    # 3. Grade by placement (header zone)
    if result.get("grade") is None:
        g = _extract_grade_by_placement(
            raw_text=raw_text,
            contact_block=contact_block,
            doc_type="ESSAY_WITH_HEADER_METADATA",
        )
        if g is not None:
            result["grade"] = g

    return result


def _extract_ifi_fallback(
    ocr_text: str,
    filename: str = None,
    fallback_reason: str | None = None,
) -> Dict[str, Any]:
    """
    Fallback extraction when no LLM is available.
    Uses simple heuristics.
    """
    from .extract_llm import parse_name_from_filename

    result = {
        'doc_type': 'UNKNOWN',
        'is_blank_template': False,
        'language': 'English',
        'student_name': None,
        'school_name': None,
        'grade': None,
        'father_figure_name': None,
        'father_figure_type': None,
        'essay_text': ocr_text if ocr_text else None,
        'parent_reaction_text': None,
        'topic': 'Father',
        'is_off_prompt': False,
        'notes': ['Fallback extraction - no LLM available'],
        'extraction_method': 'fallback',
        'model': 'none'
    }
    if fallback_reason:
        result['notes'].append(f'Fallback reason: {fallback_reason}')

    # Note: Removed filename-based name extraction - only extract from PDF document

    # Detect if blank template (no meaningful content)
    if not ocr_text or len(ocr_text.strip()) < 50:
        result['is_blank_template'] = True
        result['essay_text'] = None
        result['notes'].append('Possible blank template - very short content')
    else:
        # Freeform pattern: "Name" on one line, "School Nth grade" on next (top or bottom of doc)
        freeform = _extract_freeform_name_school_grade(ocr_text)
        if freeform:
            for k in ("student_name", "school_name", "grade"):
                if freeform.get(k) is not None:
                    result[k] = freeform[k]
            logger.info("Fallback: extracted name/school/grade from freeform pattern")

    return result


def _extract_grade_by_placement(
    raw_text: str = "",
    contact_block: str = "",
    doc_type: str = "",
) -> Optional[Any]:
    """
    Extract grade using placement- and doc-type-aware strategies.
    
    Placement strategies by doc_type:
    - IFI_OFFICIAL_TEMPLATE_BLANK, ESSAY_ONLY: No grade expected → None
    - ESSAY_WITH_HEADER_METADATA: Grade in first 1-4 lines (header zone)
      e.g. "Name\\nSchool 6th grade" or "Name, School, 3rd Grade"
    - IFI_OFFICIAL_FORM_FILLED, MULTI_ENTRY: Label proximity, then line after
      "Grade / Grado", then "Nth grade" inline with school
    """
    from pipeline.normalize import sanitize_grade

    if doc_type in ("IFI_OFFICIAL_TEMPLATE_BLANK", "ESSAY_ONLY"):
        return None

    text = (contact_block or "") + "\n" + (raw_text or "")
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    header_lines = lines[:6]  # First 6 lines for header/metadata zone
    header_text = "\n".join(header_lines)

    def _try_ordinal(s: str) -> Optional[int]:
        m = re.search(r"\b([1-9]|1[0-2])(?:st|nd|rd|th)?\s*grade\b", s, re.IGNORECASE)
        if m:
            g = int(m.group(1))
            if 1 <= g <= 12:
                return g
        m = re.search(r"(?:grade|grado)\s*[:\-/]?\s*([1-9]|1[0-2])\b", s, re.IGNORECASE)
        if m:
            g = int(m.group(1))
            if 1 <= g <= 12:
                return g
        m = re.search(r"\b([1-9]|1[0-2])\s*(?:st|nd|rd|th)?\s*(?:grade|grado)", s, re.IGNORECASE)
        if m:
            g = int(m.group(1))
            if 1 <= g <= 12:
                return g
        return None

    def _try_standalone_digit(lines_to_scan: list) -> Optional[int]:
        for ln in lines_to_scan:
            if re.match(r"^\d{1,2}$", ln):
                g = int(ln)
                if 1 <= g <= 12:
                    return g
        return None

    def _try_k(s: str) -> Optional[str]:
        if re.search(r"\b(?:k|kinder|kindergarten|pre[\s-]?k)\b", s, re.IGNORECASE):
            return "K"
        return None

    # Strategy 1: ESSAY_WITH_HEADER_METADATA – header zone only
    if doc_type == "ESSAY_WITH_HEADER_METADATA":
        g = _try_ordinal(header_text) or _try_k(header_text) or _try_standalone_digit(header_lines[:4])
        return sanitize_grade(g)

    # Strategy 2: Form-based – label proximity, then line after Grade/Grado
    if contact_block:
        from pipeline.extract import extract_value_near_label, find_grade_fallback, parse_grade, GRADE_ALIASES
        cb_lines = [ln.strip() for ln in contact_block.split("\n") if ln.strip()]
        grade_text = extract_value_near_label(cb_lines, GRADE_ALIASES, max_length=30)
        g = parse_grade(grade_text) if grade_text else None
        if g is not None:
            return sanitize_grade(g)
        g = find_grade_fallback(cb_lines)
        if g is not None:
            return sanitize_grade(g)

    # Strategy 3: "Nth grade" inline in header only (e.g. "Rachel Carson School 6th grade")
    # Do not use full text – prevents essay body contamination
    g = _try_ordinal(header_text)
    if g is not None:
        return sanitize_grade(g)

    # Strategy 4: Line immediately after "Grade / Grado"
    for i, ln in enumerate(lines[:-1]):
        if re.search(r"(?:grade|grado)", ln, re.IGNORECASE) and not re.search(r"\d", ln):
            next_ln = lines[i + 1].strip()
            g = _try_standalone_digit([next_ln]) or _try_ordinal(next_ln)
            if g is not None:
                return sanitize_grade(g)

    # Strategy 5: K variant – header/contact zone only, not essay body
    g = _try_k(header_text)
    return sanitize_grade(g)


def _extract_ifi_typed_form_by_position(raw_text: str, contact_block: str) -> Dict[str, Any]:
    """
    Position-aware extraction for IFI official typed forms.

    Layout (consistent across typed-form-submission docs):
    - Metadata fields: value on SAME line as label (right next to it):
      Student's Name, Father/Father-Figure Name, Phone, Email.
    - Block labels (content on NEXT line(s)): "Father/Father-Figure reaction to this essay",
      "What my Father or an Important Father Figure Means to Me" (essay body / parent reaction).
    - Footnote: "*A Father-Figure can be...influential males in your life."
    """
    from pipeline.document_analysis import detect_ifi_official_typed_form
    from pipeline.extract import (
        extract_value_near_label,
        find_grade_fallback,
        parse_grade,
        is_valid_value_candidate,
        looks_like_essay_fragment,
        is_plausible_student_name,
        STUDENT_NAME_ALIASES,
        SCHOOL_ALIASES,
        GRADE_ALIASES,
        PHONE_ALIASES,
        EMAIL_ALIASES,
        FATHER_FIGURE_ALIASES,
    )
    from pipeline.normalize import sanitize_grade

    text = (contact_block or "") + "\n" + (raw_text or "")
    if not detect_ifi_official_typed_form(text):
        return {}

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if len(lines) < 5:
        return {}

    # Restrict to page-1 lines for header fields (name, grade, school). Page 2 often starts with
    # contest/rules text (e.g. "JUDGING PROCESS") which must not be used as student_name.
    # Do not use "contest" alone (page 1 has "IFI Fatherhood Essay Contest").
    PAGE2_SENTINELS = (
        "judging process", "official rules", "eligibility", "rules and regulations",
        "what my father or", "father-figure can be", "influential males in your life",
    )
    page1_end = len(lines)
    for i, ln in enumerate(lines):
        low = ln.lower()
        if any(s in low for s in PAGE2_SENTINELS):
            page1_end = i
            break
    page1_lines = lines[:page1_end] if page1_end >= 5 else lines

    result = {}

    top_size = min(15, max(5, len(page1_lines) // 3))
    top_lines = page1_lines[:top_size]

    # Bottom zone: lines before footnote (Email, Phone, Father-Figure labels)
    footnote_idx = None
    for i, ln in enumerate(lines):
        if "a father-figure can be" in ln.lower() or "influential males in your life" in ln.lower():
            footnote_idx = i
            break
    if footnote_idx is not None and footnote_idx > 3:
        bottom_lines = lines[max(0, footnote_idx - 8) : footnote_idx]
    else:
        bottom_lines = lines[top_size : min(top_size + 10, len(lines))]

    # Typed form: Student's Name, Father/Father-Figure Name, Phone, Email are on the SAME line as their labels
    # Use max_length=40 and plausible-name check to avoid essay fragments (e.g. "Sayurse por que Yo", "estar junto a el")
    same_line = True
    student_name = extract_value_near_label(
        top_lines, STUDENT_NAME_ALIASES, max_length=40, same_line_only=same_line
    )
    # Reject label fragments and page-2 sentinels (must not use as student_name)
    if student_name:
        sn_low = student_name.lower().strip().replace("\u2019", "'")
        if sn_low in ("student's", "student", "student name", "student's name", "nombre del estudiante", "nombre", "estudiante"):
            student_name = None
        if student_name and ("judging process" in sn_low or "father/father-figure name" in sn_low or "nombre deo padre" in sn_low or "figura paterna" in sn_low):
            student_name = None
    if student_name and is_valid_value_candidate(student_name, max_length=40) and is_plausible_student_name(student_name, max_line_length=40):
        result["student_name"] = student_name
    else:
        # Fallback: name on NEXT line after "Student's Name" (some typed PDFs use this layout); use page1 only
        for i, ln in enumerate(page1_lines):
            ln_norm = ln.lower().strip().replace("\u2019", "'")
            if not any(alias in ln_norm for alias in ("student's name", "student name", "nombre del estudiante")):
                continue
            if i + 1 >= len(page1_lines):
                break
            candidate = page1_lines[i + 1].strip()
            if not candidate or len(candidate) > 40:
                continue
            if "@" in candidate and "." in candidate:
                continue
            low = candidate.lower()
            if any(low.startswith(w) for w in ("my father", "my mother", "my dad", "my mom", "maria,", "he ", "she ", "what ", "the ")):
                continue
            cand_low = low.replace("\u2019", "'").replace("\u2018", "'")
            if cand_low in ("student's name", "student name", "nombre del estudiante") or cand_low.startswith("student"):
                continue
            if looks_like_essay_fragment(candidate):
                continue
            if not is_plausible_student_name(candidate, max_line_length=40):
                continue
            words = candidate.split()
            if 2 <= len(words) <= 5 and all(w and w[0].isalpha() for w in words):
                result["student_name"] = candidate
                break
            if 1 <= len(words) <= 3 and candidate.replace(" ", "").replace("-", "").isalpha():
                result["student_name"] = candidate
                break
        # Fallback 2: first line after footnote (legacy layout); stay on page1
        if not result.get("student_name"):
            footnote_end = "influential males in your life"
            for i, ln in enumerate(page1_lines):
                if footnote_end in ln.lower():
                    for j in range(i + 1, min(i + 4, len(page1_lines))):
                        candidate = page1_lines[j].strip()
                        if not candidate or len(candidate) > 40:
                            continue
                        if "@" in candidate and "." in candidate:
                            result.setdefault("email", candidate)
                            break
                        low = candidate.lower()
                        if any(low.startswith(w) for w in ("my father", "my mother", "my dad", "my mom", "maria,", "he ", "she ")):
                            break
                        cand_low = low.replace("\u2019", "'").replace("\u2018", "'")
                        if cand_low in ("student's name", "student name", "nombre del estudiante") or cand_low.startswith("student"):
                            continue
                        if not is_plausible_student_name(candidate, max_line_length=40):
                            continue
                        words = candidate.split()
                        if 2 <= len(words) <= 5 and all(w[0].isalpha() for w in words if w):
                            result["student_name"] = candidate.strip()
                            break
                        elif 1 <= len(words) <= 3 and candidate.replace(" ", "").replace("-", "").isalpha():
                            result["student_name"] = candidate.strip()
                            break
                    break
        # Fallback 3: name appears later in text (page1 only; avoid page-2 content)
        if not result.get("student_name"):
            last_name_candidate = None
            for ln in page1_lines:
                candidate = ln.strip()
                if not candidate or len(candidate) > 40:
                    continue
                if "@" in candidate or (len(candidate) <= 15 and candidate.replace("-", "").replace(" ", "").isdigit()):
                    continue
                low = candidate.lower()
                if looks_like_essay_fragment(candidate):
                    continue
                if any(low.startswith(w) for w in ("my father", "my mother", "my dad", "my mom", "maria,", "he ", "she ", "what ", "the ")):
                    continue
                cand_low = low.replace("\u2019", "'").replace("\u2018", "'")
                if cand_low in ("student's name", "student name", "nombre del estudiante") or cand_low.startswith("student"):
                    continue
                if not is_plausible_student_name(candidate, max_line_length=40):
                    continue
                words = candidate.split()
                if 2 <= len(words) <= 4 and all(w and w[0].isalpha() for w in words):
                    if candidate.replace(" ", "").replace("-", "").isalpha():
                        last_name_candidate = candidate
            if last_name_candidate and is_valid_value_candidate(last_name_candidate, max_length=40):
                result["student_name"] = last_name_candidate

    grade_text = extract_value_near_label(top_lines, GRADE_ALIASES, max_length=30)
    grade = parse_grade(grade_text) if grade_text else find_grade_fallback(top_lines)
    if grade is not None:
        result["grade"] = sanitize_grade(grade)
    school_name = extract_value_near_label(top_lines, SCHOOL_ALIASES)
    # Reject label-only or essay text (e.g. "Escuela", "/ Escuela", essay fragment)
    if school_name:
        sn_low = school_name.lower().strip()
        if sn_low in ("escuela", "/ escuela", "school", "school name"):
            school_name = None
    if school_name and is_valid_value_candidate(school_name, max_length=80) and not looks_like_essay_fragment(school_name):
        result["school_name"] = school_name

    # Scavenge pass: some flattened PDFs put labels first and values many lines later (e.g. 2026 form).
    # Scan page1 for first plausible value of each type so we still get student, grade, school.
    scavenge_window = page1_lines[:50]
    _SCAVENGE_LABEL_SUBSTRINGS = (
        "student's name", "student name", "nombre del estudiante", "grade", "grado",
        "school", "escuela", "father", "padre", "figura paterna", "email", "phone", "teléfono",
        "deadline", "march", "writing about", "escribiendo sobre", "character maximum",
    )

    def _is_label_line(ln: str) -> bool:
        low = ln.lower().strip()
        return any(s in low for s in _SCAVENGE_LABEL_SUBSTRINGS) or len(low) < 2

    if not result.get("student_name"):
        # Only take a name that appears after a "Student's Name" label so we don't use father's name
        student_label_idx = -1
        for idx, ln in enumerate(scavenge_window):
            low = ln.lower().strip()
            if "student" in low and "name" in low or "nombre del estudiante" in low:
                student_label_idx = idx
                break
        for ln in scavenge_window[student_label_idx + 1 :] if student_label_idx >= 0 else []:
            cand = ln.strip()
            if not cand or _is_label_line(cand) or len(cand) > 40:
                continue
            if "@" in cand or (len(cand) <= 3 and cand.replace(".", "").isdigit()):
                continue
            if looks_like_essay_fragment(cand) or not is_plausible_student_name(cand, max_line_length=40):
                continue
            if not is_valid_value_candidate(cand, max_length=40):
                continue
            words = cand.split()
            if 2 <= len(words) <= 5 and all(w and w[0].isalpha() for w in words):
                result["student_name"] = cand
                break
    if result.get("grade") is None:
        grade_label_idx = -1
        for idx, ln in enumerate(scavenge_window):
            low = ln.lower().strip()
            if "grade" in low or "grado" in low:
                grade_label_idx = idx
                break
        for ln in scavenge_window[grade_label_idx + 1 :] if grade_label_idx >= 0 else []:
            cand = ln.strip()
            if _is_label_line(cand):
                continue
            g = parse_grade(cand)
            if g is not None:
                result["grade"] = sanitize_grade(g)
                break
    if not result.get("school_name"):
        school_label_idx = -1
        for idx, ln in enumerate(scavenge_window):
            low = ln.lower().strip()
            if "school" in low or "escuela" in low:
                school_label_idx = idx
                break
        for ln in scavenge_window[school_label_idx + 1 :] if school_label_idx >= 0 else []:
            cand = ln.strip()
            if not cand or _is_label_line(cand) or len(cand) > 80 or len(cand) < 4:
                continue
            if "@" in cand or cand.isdigit() or re.match(r"^[1-9]|1[0-2]$", cand):
                continue
            if looks_like_essay_fragment(cand) or not is_valid_value_candidate(cand, max_length=80):
                continue
            words = cand.split()
            if 2 <= len(words) <= 8 and any(w and w[0].isupper() for w in words):
                result["school_name"] = cand
                break

    # Same-line only: value right next to label
    email = extract_value_near_label(bottom_lines, EMAIL_ALIASES, max_length=80, same_line_only=same_line)
    if email and "@" in email and "." in email:
        result["email"] = email
    phone = extract_value_near_label(bottom_lines, PHONE_ALIASES, max_length=30, same_line_only=same_line)
    if phone:
        result["phone"] = phone
    father_figure_name = extract_value_near_label(
        bottom_lines, FATHER_FIGURE_ALIASES, max_length=80, same_line_only=same_line
    )
    if father_figure_name:
        low = father_figure_name.lower()
        if not any(
            phrase in low
            for phrase in (" is ", " was ", " he ", " she ", " my father ", " my mother ")
        ) and len(father_figure_name.split()) <= 5:
            result["father_figure_name"] = father_figure_name

    # Final sanitization: never return known labels as student_name or school_name (agentic pipeline stays clean)
    if result.get("student_name"):
        low = result["student_name"].lower().strip().replace("\u2019", "'")
        if any(x in low for x in ("father/father-figure name", "nombre del padre", "nombre deo padre", "figura paterna", "judging process")):
            del result["student_name"]
    if result.get("school_name"):
        low = result["school_name"].lower().strip()
        if low in ("escuela", "/ escuela", "school", "school name"):
            del result["school_name"]

    return result


# For backward compatibility with existing pipeline
def extract_fields_ifi(
    contact_block: str,
    raw_text: str = "",
    original_filename: str = None,
    form_field_values: Optional[Dict[str, str]] = None,
    doc_format: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Wrapper function compatible with existing pipeline interface.

    When form_field_values is provided (from PDF AcroForm widgets), values such as
    "Student's Name" are used as the source of truth and override text-derived extraction.

    Doc-type detection drives processing:
    - IFI typed form (layout + consistent labels): rule-based extraction only, no OCR, no LLM
    - Typed freeform (native_text, not official form): header-only text → dedicated Groq prompt for name/school/grade
    - Other docs: full-doc LLM extraction with fallbacks

    Returns fields in the format expected by the pipeline:
    {
        'student_name': str | None,
        'school_name': str | None,
        'grade': int | str | None,
        'teacher_name': None,
        'city_or_location': None,
        'father_figure_name': str | None,
        'phone': None,
        'email': None,
        '_ifi_metadata': {full IFI extraction result}
    }
    """
    from pipeline.document_analysis import detect_ifi_official_typed_form
    from pipeline.extract_llm import _extract_phone_fallback, _extract_email_fallback
    from pipeline.extract import is_plausible_student_name

    # Authoritative values from form fields when present (filled AcroForm is source of truth)
    # Reject form values that are labels/sentinels so pipeline never gets them
    def _form_value_student(v):
        if not v or not str(v).strip():
            return None
        low = str(v).strip().lower().replace("\u2019", "'")
        if any(x in low for x in ("father/father-figure name", "nombre del padre", "nombre deo padre", "figura paterna", "judging process")):
            return None
        return v.strip()
    def _form_value_school(v):
        if not v or not str(v).strip():
            return None
        low = str(v).strip().lower()
        if low in ("escuela", "/ escuela", "school", "school name"):
            return None
        return v.strip()

    form_student_name = None
    form_grade = None
    form_school = None
    form_father_figure_name = None
    if form_field_values:
        if form_field_values.get("Student's Name"):
            v = _form_value_student(form_field_values["Student's Name"])
            if v:
                form_student_name = v
        if form_field_values.get("Grade"):
            v = (form_field_values["Grade"] or "").strip()
            if v:
                form_grade = _normalize_grade(v)
        if form_field_values.get("School"):
            v = _form_value_school(form_field_values["School"])
            if v:
                form_school = v
        if form_field_values.get("Dad's Name"):
            v = (form_field_values["Dad's Name"] or "").strip()
            if v:
                form_father_figure_name = v

    text = (contact_block or "") + "\n" + (raw_text or "")
    is_ifi_typed_form = detect_ifi_official_typed_form(text)

    if is_ifi_typed_form:
        # Typed form: rule-based extraction only (no OCR, no LLM)
        typed_form_fields = _extract_ifi_typed_form_by_position(raw_text, contact_block)
        phone = typed_form_fields.get("phone")
        email = typed_form_fields.get("email")
        if (phone is None or email is None) and contact_block:
            if phone is None:
                phone = _extract_phone_fallback(contact_block)
            if email is None:
                email = _extract_email_fallback(contact_block)
        ifi_result = {
            "doc_type": "IFI_OFFICIAL_FORM_FILLED",
            "is_blank_template": False,
            "extraction_method": "typed_form_rule_based",
            "notes": ["IFI typed form: extracted via layout/label rules (no OCR, no LLM)"],
            **(typed_form_fields or {}),
            "phone": phone,
            "email": email,
        }
        logger.info("IFI typed form detected: using rule-based extraction (no LLM)")
    else:
        # Typed freeform (native_text): heuristics extract → Groq normalize
        is_typed_freeform = (doc_format == "native_text")
        ifi_result = None
        if is_typed_freeform:
            heuristic_result = _extract_freeform_heuristics(contact_block, raw_text)
            header_text = _get_freeform_header_text(contact_block, raw_text)
            normalized = _normalize_freeform_metadata_via_groq(header_text, heuristic_result)
            # Use Groq-normalized result if available, else heuristics only
            name_school_grade = normalized if normalized else heuristic_result
            ifi_result = {
                "doc_type": "ESSAY_WITH_HEADER_METADATA",
                "is_blank_template": False,
                "extraction_method": "llm_ifi_freeform_heuristics_then_groq_normalize" if normalized else "freeform_heuristics_only",
                "notes": ["Typed freeform: heuristics extract → Groq normalize"] if normalized else ["Typed freeform: heuristics only (Groq unavailable)"],
                "student_name": name_school_grade.get("student_name"),
                "school_name": name_school_grade.get("school_name"),
                "grade": name_school_grade.get("grade"),
                "essay_text": (raw_text or "").strip() or None,
                "father_figure_name": None,
                "father_figure_type": None,
                "parent_reaction_text": None,
                "topic": "Father",
                "is_off_prompt": False,
                "language": "English",
            }
            logger.info("Typed freeform: heuristics → Groq normalize" if normalized else "Typed freeform: heuristics only")
        if ifi_result is None:
            # Other non-typed-form: heuristics first, then full-doc LLM to fill missing
            heuristic_result = _extract_freeform_heuristics(contact_block, raw_text)
            ifi_result = extract_ifi_submission(raw_text, contact_block, None, original_filename)
            for k in ("student_name", "school_name", "grade"):
                if heuristic_result.get(k) is not None:
                    ifi_result[k] = heuristic_result[k]
                    logger.info(f"Freeform heuristics: {k}={heuristic_result[k]!r}")

        typed_form_fields = _extract_ifi_typed_form_by_position(raw_text, contact_block)
        if typed_form_fields:
            for k, v in typed_form_fields.items():
                if v is not None and (ifi_result.get(k) is None or k in ("grade", "school_name", "student_name")):
                    ifi_result[k] = v
                    logger.info(f"IFI typed form extraction: {k}={v!r}")

        phone = typed_form_fields.get("phone") if typed_form_fields else None
        email = typed_form_fields.get("email") if typed_form_fields else None
        if (phone is None or email is None) and contact_block:
            if phone is None:
                phone = _extract_phone_fallback(contact_block)
            if email is None:
                email = _extract_email_fallback(contact_block)
    
    # Fallback: Placement- and doc-type-aware grade extraction
    grade = ifi_result.get('grade')
    doc_type = ifi_result.get('doc_type', '')
    if grade is None:
        grade = _extract_grade_by_placement(
            raw_text=raw_text,
            contact_block=contact_block,
            doc_type=doc_type,
        )
        if grade is not None:
            ifi_result['grade'] = grade
            logger.info(f"Fallback: Found grade {grade} (doc_type={doc_type}, placement-aware)")

    # Start with extracted student_name; form field or fallback may override
    student_name = ifi_result.get('student_name')

    # Fallback: If LLM didn't extract student_name, try rule-based extraction from contact_block
    # Skip for typed forms (already did position-aware extraction; fallback can return labels)
    if not student_name and contact_block and not is_ifi_typed_form:
        from pipeline.extract import extract_value_near_label, STUDENT_NAME_ALIASES
        lines = [line.strip() for line in contact_block.split('\n') if line.strip()]
        student_name = extract_value_near_label(lines, STUDENT_NAME_ALIASES, max_length=40)
        if student_name:
            low = student_name.lower()
            if low not in ("student's name", "student name", "student's", "nombre del estudiante"):
                if is_plausible_student_name(student_name, max_line_length=40):
                    logger.info(f"Fallback extraction found student_name: {student_name}")
                    ifi_result['student_name'] = student_name
                    if 'notes' not in ifi_result:
                        ifi_result['notes'] = []
                    ifi_result['notes'].append(f"Student name extracted via fallback rule-based method: {student_name}")
                else:
                    student_name = None
            else:
                student_name = None

    # Fallback: Freeform pattern "Name" on one line, "School Nth grade" on next (top or bottom of doc)
    if not is_ifi_typed_form and text:
        missing = (
            (ifi_result.get('student_name') is None) or
            (ifi_result.get('school_name') is None) or
            (ifi_result.get('grade') is None)
        )
        if missing:
            freeform = _extract_freeform_name_school_grade(text)
            if freeform:
                for k in ("student_name", "school_name", "grade"):
                    if freeform.get(k) is not None and ifi_result.get(k) is None:
                        ifi_result[k] = freeform[k]
                        logger.info(f"Freeform pattern: {k}={freeform[k]!r}")
                if freeform.get("student_name"):
                    student_name = student_name or freeform["student_name"]

    # Prefer form field values when present (source of truth for fillable PDFs)
    if form_student_name:
        student_name = form_student_name
        ifi_result["student_name"] = form_student_name
    if form_grade is not None:
        ifi_result["grade"] = form_grade
    if form_school:
        ifi_result["school_name"] = form_school
    if form_father_figure_name:
        ifi_result["father_figure_name"] = form_father_figure_name

    # Map to pipeline format (form "Dad's Name" overrides text extraction so we don't get "or" from the label)
    father_figure_name = form_father_figure_name or ifi_result.get("father_figure_name")
    # Reject label fragments (bilingual label: "Father/Father-Figure Name / Nombre del Padre/Figura Paterna")
    if father_figure_name:
        low = father_figure_name.strip().lower()
        label_fragments = (
            "or", "and", "father", "figure", "name", "padre", "father-figure", "father-figure name",
            "nombre del padre", "figura paterna", "nombre del padre/figura paterna",
        )
        if low in label_fragments or low.replace("/", " ").strip() in label_fragments:
            father_figure_name = None

    # Never pass label/sentinel strings as student_name or school_name into the pipeline record
    def _is_label_student_name(v):
        if not v or not str(v).strip():
            return True
        low = str(v).strip().lower().replace("\u2019", "'")
        return any(x in low for x in ("father/father-figure name", "nombre del padre", "nombre deo padre", "figura paterna", "judging process"))
    def _is_label_school_name(v):
        if not v or not str(v).strip():
            return True
        low = str(v).strip().lower()
        return low in ("escuela", "/ escuela", "school", "school name")

    out_student = student_name or ifi_result.get("student_name")
    out_school = ifi_result.get("school_name")
    if out_student and _is_label_student_name(out_student):
        out_student = None
    if out_school and _is_label_school_name(out_school):
        out_school = None

    pipeline_fields = {
        'student_name': out_student,
        'school_name': out_school,
        'grade': ifi_result.get('grade'),
        'teacher_name': None,
        'city_or_location': None,
        'father_figure_name': father_figure_name,
        'phone': phone,
        'email': email,
        '_ifi_metadata': ifi_result  # Store full IFI result for reference
    }
    
    return pipeline_fields
