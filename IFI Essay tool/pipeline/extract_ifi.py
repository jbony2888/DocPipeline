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
    # Check for API keys
    openai_key = os.environ.get("OPENAI_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")
    
    if not openai_key and not groq_key:
        logger.warning("No LLM API keys set - falling back to basic extraction")
        return _extract_ifi_fallback(raw_ocr_text, original_filename)
    
    try:
        # Use OpenAI if available (best for complex classification)
        if openai_key:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            model_name = "gpt-4o"
            provider = "openai"
        else:
            from groq import Groq
            client = Groq(api_key=groq_key)
            model_name = "llama-3.3-70b-versatile"
            provider = "groq"
        
        # Build comprehensive prompt
        prompt = _build_ifi_extraction_prompt(raw_ocr_text, original_filename)
        
        # Call LLM
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at classifying and extracting data from educational contest submissions. Return only valid JSON."
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
        logger.error(f"IFI LLM extraction failed: {e}")
        return _extract_ifi_fallback(raw_ocr_text, original_filename)


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

Extract these fields (DO NOT GUESS - only extract if explicitly present):

student_name (string | null):
- From "Student's Name / Nombre del Estudiante" label (official forms)
- From first line (header metadata format)
- DO NOT extract from filename - only from PDF document content
- Correct OCR errors (e.g., "Alv4rez" -> "Alvarez")
- null if not found

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
- DO NOT hallucinate missing values - use null
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
        
        # Extract digits
        digits = re.search(r'\d+', grade_str)
        if digits:
            grade_int = int(digits.group())
            if 1 <= grade_int <= 12:
                return grade_int
    
    return None


def _extract_ifi_fallback(ocr_text: str, filename: str = None) -> Dict[str, Any]:
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
    
    # Note: Removed filename-based name extraction - only extract from PDF document
    
    # Detect if blank template (no meaningful content)
    if not ocr_text or len(ocr_text.strip()) < 50:
        result['is_blank_template'] = True
        result['essay_text'] = None
        result['notes'].append('Possible blank template - very short content')
    
    return result


# For backward compatibility with existing pipeline
def extract_fields_ifi(contact_block: str, raw_text: str = "", 
                       original_filename: str = None) -> Dict[str, Any]:
    """
    Wrapper function compatible with existing pipeline interface.
    
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
    # Run full IFI extraction
    ifi_result = extract_ifi_submission(raw_text, contact_block, None, original_filename)
    
    # Fallback extraction for phone and email (IFI prompt doesn't extract these)
    from pipeline.extract_llm import _extract_phone_fallback, _extract_email_fallback
    
    phone = None
    email = None
    if contact_block:
        phone = _extract_phone_fallback(contact_block)
        email = _extract_email_fallback(contact_block)
    
    # Map to pipeline format
    pipeline_fields = {
        'student_name': ifi_result.get('student_name'),
        'school_name': ifi_result.get('school_name'),
        'grade': ifi_result.get('grade'),
        'teacher_name': None,
        'city_or_location': None,
        'father_figure_name': ifi_result.get('father_figure_name'),
        'phone': phone,
        'email': email,
        '_ifi_metadata': ifi_result  # Store full IFI result for reference
    }
    
    return pipeline_fields


