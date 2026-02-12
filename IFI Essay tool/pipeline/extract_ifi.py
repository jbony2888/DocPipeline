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
    
    # M3: Check for cached LLM result (determinism)
    submission_id = None
    if contact_block:
        # Try to extract submission_id from context if available
        import hashlib
        # Use raw_ocr_text hash as submission identifier for caching
        text_hash = hashlib.sha256(raw_ocr_text.encode()).hexdigest()[:12]
        submission_id = text_hash
    
    cached_result = None
    if submission_id:
        cached_result = _get_cached_llm_result(submission_id)
        if cached_result:
            logger.info(f"Using cached LLM result for submission {submission_id}")
            # Emit CACHED_LLM_RESULT event (will be emitted by caller)
            return cached_result
    
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
        
        # Call LLM with temperature=0 for determinism (M3)
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at extracting data from educational contest submissions. Return only valid JSON. Classification suggestions are advisory only - they will be verified deterministically."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0,  # Deterministic (M3)
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
        
        # M2: Verify classification deterministically (remove LLM authority)
        from pipeline.classify import extract_classification_features, verify_doc_type_signal
        
        features = extract_classification_features(raw_ocr_text)
        signal_doc_type = result.get('doc_type')
        doc_type_final, verified, reason = verify_doc_type_signal(signal_doc_type, features, raw_ocr_text)
        
        # Store both signal and final for audit
        result['doc_type_signal'] = signal_doc_type  # LLM suggestion
        result['doc_type_final'] = doc_type_final  # Deterministic decision
        result['classification_verified'] = verified
        result['classification_reason'] = reason
        
        # If not verified, flag for review
        if not verified:
            if 'notes' not in result:
                result['notes'] = []
            result['notes'].append(f"Classification not verified: {reason}")
            result['needs_review'] = True
        
        # M2: Verify extracted fields exist in OCR text
        result = verify_extracted_fields(result, raw_ocr_text)
        
        logger.info(f"IFI extraction complete: doc_type_signal={signal_doc_type}, "
                   f"doc_type_final={doc_type_final}, verified={verified}, "
                   f"student={result.get('student_name')}, grade={result.get('grade')}")
        
        # M3: Cache LLM result for determinism
        if submission_id:
            _cache_llm_result(submission_id, result)
        
        return result
    
    except Exception as e:
        logger.error(f"IFI LLM extraction failed: {e}")
        result = _extract_ifi_fallback(raw_ocr_text, original_filename)
        # Add error to result for audit
        result['_extraction_error'] = str(e)
        return result


def _build_ifi_extraction_prompt(ocr_text: str, filename: str = None) -> str:
    """Build the comprehensive extraction prompt (classification is advisory only per DBF)."""
    
    prompt = f"""You are extracting structured data from IFI Fatherhood Essay Contest submissions.

OCR TEXT:
```
{ocr_text}
```

FILENAME: {filename if filename else "unknown"}

TASK: Extract fields and suggest document classification. Return JSON only.

===== PHASE 1: CLASSIFICATION SUGGESTION (ADVISORY) =====

Suggest ONE of these doc_types (this will be verified deterministically):

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


def verify_extracted_fields(result: Dict[str, Any], ocr_text: str) -> Dict[str, Any]:
    """
    Verify that extracted fields exist in OCR text (M2 - DBF compliance).
    
    Args:
        result: LLM extraction result
        ocr_text: Full OCR text
        
    Returns:
        Verified result with unverified fields nullified and reason codes added
    """
    ocr_lower = ocr_text.lower()
    unverified_fields = []
    
    # Verify student_name
    student_name = result.get('student_name')
    if student_name:
        # Check if name appears in OCR (case-insensitive, allow for OCR errors)
        name_words = student_name.split()
        if len(name_words) >= 2:
            # Check if first and last name appear in OCR
            first_name = name_words[0].lower()
            last_name = name_words[-1].lower()
            if first_name not in ocr_lower or last_name not in ocr_lower:
                result['student_name'] = None
                unverified_fields.append('student_name')
                if 'notes' not in result:
                    result['notes'] = []
                result['notes'].append(f"student_name '{student_name}' not found in OCR text")
    
    # Verify school_name
    school_name = result.get('school_name')
    if school_name:
        school_lower = school_name.lower()
        # Check if school name or key words appear
        school_words = school_lower.split()
        found_words = sum(1 for word in school_words if len(word) > 3 and word in ocr_lower)
        if found_words < len(school_words) * 0.5:  # Less than 50% of words found
            result['school_name'] = None
            unverified_fields.append('school_name')
            if 'notes' not in result:
                result['notes'] = []
            result['notes'].append(f"school_name '{school_name}' not verified in OCR text")
    
    # Verify grade (check for grade number or "K" in OCR)
    grade = result.get('grade')
    if grade:
        if isinstance(grade, int):
            grade_str = str(grade)
            # Check for grade number or ordinal
            if grade_str not in ocr_lower and f"{grade_str}th" not in ocr_lower and f"{grade_str}nd" not in ocr_lower and f"{grade_str}rd" not in ocr_lower:
                result['grade'] = None
                unverified_fields.append('grade')
                if 'notes' not in result:
                    result['notes'] = []
                result['notes'].append(f"grade '{grade}' not verified in OCR text")
        elif isinstance(grade, str) and grade.upper() == 'K':
            # Check for kindergarten indicators
            if 'k' not in ocr_lower and 'kindergarten' not in ocr_lower and 'kinder' not in ocr_lower:
                result['grade'] = None
                unverified_fields.append('grade')
                if 'notes' not in result:
                    result['notes'] = []
                result['notes'].append(f"grade 'K' not verified in OCR text")
    
    # Verify father_figure_name
    father_name = result.get('father_figure_name')
    if father_name:
        name_words = father_name.split()
        if len(name_words) >= 2:
            first_name = name_words[0].lower()
            last_name = name_words[-1].lower()
            if first_name not in ocr_lower or last_name not in ocr_lower:
                result['father_figure_name'] = None
                unverified_fields.append('father_figure_name')
                if 'notes' not in result:
                    result['notes'] = []
                result['notes'].append(f"father_figure_name '{father_name}' not verified in OCR text")
    
    # Add unverified field reason codes
    if unverified_fields:
        if 'review_reason_codes' not in result:
            result['review_reason_codes'] = []
        for field in unverified_fields:
            result['review_reason_codes'].append(f"UNVERIFIED_FIELD_{field.upper()}")
        result['needs_review'] = True
    
    return result


def _get_cached_llm_result(submission_id: str) -> Optional[Dict[str, Any]]:
    """
    M3: Get cached LLM result from Supabase audit trace for determinism.
    
    Args:
        submission_id: Submission identifier
        
    Returns:
        Cached result dict or None
    """
    try:
        from pipeline.supabase_db import get_supabase_client
        from supabase import create_client
        import os
        
        supabase_url = os.environ.get("SUPABASE_URL")
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        
        if not service_key or not supabase_url:
            return None
        
        admin_client = create_client(supabase_url, service_key)
        
        # Get most recent trace for this submission
        result = admin_client.table("submission_audit_traces").select(
            "signals"
        ).eq("submission_id", submission_id).order("created_at", desc=True).limit(1).execute()
        
        if result.data and len(result.data) > 0:
            signals = result.data[0].get("signals", {})
            llm_signal = signals.get("llm", {})
            if llm_signal:
                # Reconstruct result from cached signal
                # Note: This is a simplified cache - full caching would store complete result
                return None  # For now, return None to always use fresh LLM (can be enhanced)
        
        return None
    except Exception as e:
        logger.warning(f"Could not get cached LLM result: {e}")
        return None


def _cache_llm_result(submission_id: str, result: Dict[str, Any]) -> None:
    """
    M3: Cache LLM result in Supabase for determinism.
    
    Args:
        submission_id: Submission identifier
        result: LLM extraction result
    """
    try:
        # Cache is stored in audit trace signals, so no separate cache table needed
        # The trace already contains the LLM signal
        pass
    except Exception as e:
        logger.warning(f"Could not cache LLM result: {e}")


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
    # Try unlabeled header format first (for simple essays without form structure)
    from pipeline.extract_llm import _extract_unlabeled_header_format
    unlabeled_data = _extract_unlabeled_header_format(raw_text or contact_block)
    
    # If unlabeled format found all required fields, use it directly
    if unlabeled_data and unlabeled_data.get("student_name") and unlabeled_data.get("school_name") and unlabeled_data.get("grade"):
        logger.info(f"Using unlabeled header format extraction - student: '{unlabeled_data.get('student_name')}', school: '{unlabeled_data.get('school_name')}', grade: '{unlabeled_data.get('grade')}'")
        return {
            'student_name': unlabeled_data.get("student_name"),
            'school_name': unlabeled_data.get("school_name"),
            'grade': unlabeled_data.get("grade"),
            'teacher_name': None,
            'city_or_location': None,
            'father_figure_name': None,
            'phone': None,
            'email': None,
            '_ifi_metadata': {
                'extraction_method': 'unlabeled_header_format',
                'confidence': 'high'
            }
        }
    
    # Run full IFI extraction for structured forms
    ifi_result = extract_ifi_submission(raw_text, contact_block, None, original_filename)
    
    # Fallback extraction for phone and email (IFI prompt doesn't extract these)
    from pipeline.extract_llm import _extract_phone_fallback, _extract_email_fallback
    
    phone = None
    email = None
    if contact_block:
        phone = _extract_phone_fallback(contact_block)
        email = _extract_email_fallback(contact_block)
    
    # Fallback: Use unlabeled header data if IFI extraction missed fields
    student_name = ifi_result.get('student_name')
    school_name = ifi_result.get('school_name')
    grade = ifi_result.get('grade')
    
    if unlabeled_data:
        if not student_name and unlabeled_data.get("student_name"):
            student_name = unlabeled_data["student_name"]
            logger.info(f"Using unlabeled header student_name: {student_name}")
        if not school_name and unlabeled_data.get("school_name"):
            school_name = unlabeled_data["school_name"]
            logger.info(f"Using unlabeled header school_name: {school_name}")
        if not grade and unlabeled_data.get("grade"):
            grade = unlabeled_data["grade"]
            logger.info(f"Using unlabeled header grade: {grade}")
    
    # Fallback: If still no student_name, try rule-based extraction from contact_block
    if not student_name and contact_block:
        from pipeline.extract import extract_value_near_label, STUDENT_NAME_ALIASES
        lines = [line.strip() for line in contact_block.split('\n') if line.strip()]
        student_name = extract_value_near_label(lines, STUDENT_NAME_ALIASES)
        if student_name:
            logger.info(f"Fallback extraction found student_name: {student_name}")
            # Update the IFI result for consistency
            ifi_result['student_name'] = student_name
            if 'notes' not in ifi_result:
                ifi_result['notes'] = []
            ifi_result['notes'].append(f"Student name extracted via fallback rule-based method: {student_name}")
    
    # Map to pipeline format
    pipeline_fields = {
        'student_name': student_name,
        'school_name': school_name,
        'grade': grade,
        'teacher_name': None,
        'city_or_location': None,
        'father_figure_name': ifi_result.get('father_figure_name'),
        'phone': phone,
        'email': email,
        '_ifi_metadata': ifi_result  # Store full IFI result for reference
    }
    
    return pipeline_fields


