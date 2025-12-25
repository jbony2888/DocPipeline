"""
LLM-based extraction using Groq API.
Handles complex bilingual forms and OCR noise better than rule-based extraction.
"""

import os
import json
import re
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def parse_name_from_filename(filename: str) -> Optional[str]:
    """
    Extract student name from filename.
    
    Examples:
        "Andres-Alvarez-Olguin.pdf" -> "Andres Alvarez Olguin"
        "John-Michael-Smith.jpg" -> "John Michael Smith"
    
    Args:
        filename: Original uploaded filename
        
    Returns:
        Parsed name or None if unable to parse
    """
    if not filename:
        return None
    
    # Remove file extension
    name_part = Path(filename).stem
    
    # Replace hyphens and underscores with spaces
    name_part = name_part.replace('-', ' ').replace('_', ' ')
    
    # Remove any numbers or special characters
    name_part = re.sub(r'[0-9\(\)\[\]{}]', '', name_part)
    
    # Clean up multiple spaces
    name_part = ' '.join(name_part.split())
    
    # Capitalize each word properly
    name_part = ' '.join(word.capitalize() for word in name_part.split())
    
    # Only return if it looks like a valid name (2+ words, each 2+ chars)
    words = name_part.split()
    if len(words) >= 2 and all(len(w) >= 2 for w in words):
        return name_part
    
    return None


def extract_fields_llm(contact_block: str, raw_text: str = "", original_filename: str = None) -> dict:
    """
    Extract structured fields using LLM (OpenAI or Groq).
    
    Uses LLM inference to intelligently extract fields from messy OCR text.
    Handles bilingual forms, OCR errors, and complex layouts.
    
    Priority: OpenAI (highest accuracy) > Groq (fast, free)
    
    Args:
        contact_block: Text containing contact information
        raw_text: Full OCR text (optional, for additional context)
        original_filename: Original filename (e.g., "Andres-Alvarez-Olguin.pdf") to extract name as fallback
        
    Returns:
        dict with extracted fields (same format as extract_fields_rules)
    """
    # Check for OpenAI first (highest accuracy)
    openai_key = os.environ.get("OPENAI_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")
    
    if not openai_key and not groq_key:
        logger.warning("No API keys set (OPENAI_API_KEY or GROQ_API_KEY), LLM extraction unavailable")
        # Return all nulls - don't extract name from filename
        return {
            "student_name": None,
            "school_name": None,
            "grade": None,
            "teacher_name": None,
            "city_or_location": None,
            "father_figure_name": None,
            "phone": None,
            "email": None
        }
    
    try:
        # Use OpenAI if key is available (best accuracy)
        if openai_key:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            model_name = "gpt-4o-mini"
            provider = "openai"
        else:
            # Fall back to Groq (free, fast)
            from groq import Groq
            client = Groq(api_key=groq_key)
            model_name = "llama-3.3-70b-versatile"  # Updated: mixtral was decommissioned
            provider = "groq"
        
        # Construct extraction prompt
        prompt = f"""You are extracting data from a handwritten bilingual essay contest form. The OCR has MANY errors.

**OCR TEXT:**
{contact_block}

**YOUR TASK:** Extract these fields as JSON. Use context and intelligence to correct OCR errors:

1. **student_name**: Student's FULL name (first + middle + last if present)
   - Labels: "Student's Name", "Nombre del Estudiante", or just "Name"
   - **CRITICAL:** Often appears multiple times with different OCR errors
   - Look for ALL name variations in the text and combine to get the full name
   - Example pattern: "John M1chael" (line 5) + "Smith" (line 8) → "John Michael Smith"
   - Names often appear near the TOP of the form (first 15 lines)
   - Spanish names commonly have 3 parts: First Middle Last - capture all if present

2. **school_name**: School name
   - Labels: "School", "Escuela"  
   - **CRITICAL:** Value is almost ALWAYS on the line IMMEDIATELY BEFORE the "School" label!
   - Example pattern you'll see:
     ```
     Lnc0ln Elem        ← Value (may be OCR-corrupted)
     School             ← Label
     Escuela            ← Spanish label
     ```
   - Look for the line RIGHT BEFORE "School"/"Escuela" appears
   - OCR often corrupts school names - try to infer/correct common patterns
   - Common school types: "Elementary", "Middle School", "High School", "Academy"
   
3. **grade**: Integer 1-12 only (return as number, not string!)
   - Labels: "Grade", "Grado", "Grade / Grado"
   - **CRITICAL PRIORITY 1:** Check the line IMMEDIATELY AFTER "Grade / Grado" or "Grade" or "Grado" label
     - Sometimes the grade appears right after the label on the next line
     - **IMPORTANT:** If the line after "Grade / Grado" is EMPTY or contains "Deadline:" or a date, the grade field was likely BLANK (OCR didn't capture handwritten grade)
     - In that case, the grade cannot be extracted from OCR - return null
     - Example pattern:
       ```
       Grade / Grado
       1              ← Check this line first! (grade found)
       Deadline:
       ```
     - Or blank case:
       ```
       Grade / Grado
       Deadline:      ← Grade field is blank, OCR didn't capture it
       March 19       ← Return null for grade
       ```
   - **CRITICAL PRIORITY 2:** Look for ordinal formats on the same line or nearby:
     - "1st", "1st Grade", "first", "First Grade"
     - "2nd", "3rd", "4th", etc.
     - "Primero", "Segundo", etc. (Spanish: first, second)
     - Parse these to integers: "1st" → 1, "2nd" → 2, etc.
   - **CRITICAL PRIORITY 3:** Search the ENTIRE text for a standalone digit 1-12 on its own line
     - Pattern examples:
       ```
       ...lots of text...
       *
       10           ← This might be the grade!
       2000 Character Maximum
       ```
   - Look for lines containing ONLY these: "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"
   - DON'T extract from: phone numbers ("773 414.7126"), dates ("March 19"), "3000 Character Maximum", "2000 Character Maximum"
   - **Search strategy:** 
     1. FIRST: Check line immediately after "Grade / Grado" label (most common location)
     2. SECOND: Look for ordinal formats like "1st", "1st Grade", "first grade" anywhere near grade labels
     3. THIRD: Scan ALL lines sequentially for standalone digits 1-12
   - Valid grades: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12
   - If multiple candidates found, prefer the one closest to the "Grade" label or immediately after it
   
4. **teacher_name**: Teacher's name (often missing, that's OK)

5. **city_or_location**: City/state (might be in header)

6. **father_figure_name**: Father or father figure's actual name (real person)
   - Labels: "Father", "Padre", "Father-Figure Name", "Nombre del Padre"
   - Look for an actual person's name (pattern: FirstName LastName)
   - **DON'T extract these (they're form text, not names):**
     - State names (Illinois, Texas, etc.)
     - "Fatherhood" or "Fatherhood Initiative" (contest name)
     - "Father" / "Padre" (just the label)
     - Checkbox options: "Grandfather", "Stepdad", "Uncle"
   - Look for a real person's name near the father label (typically 2-3 words)

7. **phone**: Phone number (clean format preferred)
   - Labels: "Phone", "Teléfono", "Telefono"
   - Format: XXX-XXX-XXXX or similar
   - OCR may corrupt digits or add "/" characters (e.g., "1/2" might be "12")
   - Try to clean/normalize if possible, or keep OCR output if unclear

8. **email**: Email address
   - Labels: "Email", "Correo"
   - Format: name@domain.com
   - **CRITICAL:** OCR often corrupts emails severely
   - If you see corrupted text near "Email" label, try to infer based on context:
     - Use student's last name as username hint
     - Common domains: @gmail.com, @yahoo.com, @hotmail.com
   - Example pattern: corrupted "jdoe@ gm" + name "John Doe" → likely "jdoe@gmail.com"

**CRITICAL RULES:**
- Ignore header/form text: state names, "IFI", "Fatherhood Initiative", "Deadline", "Contest", "Character Maximum"
- Correct OCR errors intelligently:
  - Common OCR substitutions: "l" ↔ "I", "0" ↔ "O", "5" ↔ "S"
  - Merge name fragments from multiple lines if they appear to be parts of the same name
  - Fix obvious corruptions in school names, emails
- Look for STANDALONE digits (1-12) for grade on their own line
- Spanish names often have 3 parts: First Middle Last - capture all parts
- For corrupted emails, use context (student name) to infer likely address
- Return null if truly not found (don't guess wildly)

**PATTERN EXAMPLES** (illustrative only, actual values will vary):
- student_name: Combine fragments → "John Michael Smith" not just "John Smith"
- school_name: Often right BEFORE "School" label → corrupt "Lnc0ln" → "Lincoln School"
- grade: 
  - PRIORITY: Check line after "Grade / Grado" → "Grade / Grado" followed by "1" or "1st" → grade is 1
  - Ordinal format: "1st Grade" → grade is 1, "2nd" → grade is 2
  - Standalone digit: look for "7" or "10" on its own line (but verify it's not part of "2000 Character Maximum")
- father_figure_name: Actual person name → "Carlos Garcia" NOT "Grandfather" or "Illinois"
- phone: Clean format → "555 1/2 3456" → "555-123-4456"  
- email: Infer if corrupted → "jsmith@ gm" + name "Smith" → "jsmith@gmail.com"

Return ONLY valid JSON, no markdown, no explanation."""

        # Call LLM API
        if provider == "openai":
            # OpenAI GPT-4o-mini - highest accuracy
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a data extraction assistant. Return only valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,  # Low temperature for consistent extraction
                max_tokens=500,
                response_format={"type": "json_object"}  # Force JSON output
            )
        else:
            # Groq (Mixtral) - fast and free
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a data extraction assistant. Return only valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
        
        # Parse response
        result_text = response.choices[0].message.content
        result = json.loads(result_text)
        
        # Validate and normalize the result
        normalized = {
            "student_name": result.get("student_name"),
            "school_name": result.get("school_name"),
            "grade": None,
            "teacher_name": result.get("teacher_name"),
            "city_or_location": result.get("city_or_location"),
            "father_figure_name": result.get("father_figure_name"),
            "phone": result.get("phone"),
            "email": result.get("email")
        }
        
        # Validate grade is an integer 1-12
        grade_raw = result.get("grade")
        grade_found = False
        if grade_raw is not None:
            try:
                # Handle string inputs like "1st", "first", etc.
                if isinstance(grade_raw, str):
                    import re
                    # Try to extract number from ordinals: "1st", "2nd", "first", etc.
                    ordinal_match = re.search(r'\b(\d+)(?:st|nd|rd|th)\b', grade_raw.lower())
                    if ordinal_match:
                        grade_int = int(ordinal_match.group(1))
                    else:
                        # Try "first", "second", etc.
                        ordinal_words = {
                            "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
                            "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
                            "eleventh": 11, "twelfth": 12,
                            "primero": 1, "segundo": 2, "tercero": 3, "cuarto": 4, "quinto": 5,
                            "sexto": 6, "séptimo": 7, "octavo": 8, "noveno": 9, "décimo": 10
                        }
                        grade_lower = grade_raw.lower().strip()
                        if grade_lower in ordinal_words:
                            grade_int = ordinal_words[grade_lower]
                        else:
                            # Extract any digit from the string
                            digit_match = re.search(r'\b(\d{1,2})\b', grade_raw)
                            if digit_match:
                                grade_int = int(digit_match.group(1))
                            else:
                                grade_int = int(grade_raw)
                else:
                    grade_int = int(grade_raw)
                
                if 1 <= grade_int <= 12:
                    normalized["grade"] = grade_int
                    grade_found = True
            except (ValueError, TypeError):
                pass
        
        # Fallback: Check line immediately after "Grade / Grado" label if LLM didn't find grade
        if not grade_found:
            import re
            lines = contact_block.split('\n')
            for i, line in enumerate(lines):
                # Check if this line contains grade label
                line_lower = line.lower()
                if ('grade' in line_lower or 'grado' in line_lower) and ('/' in line or 'grade' in line_lower):
                    # Check if the next line is blank/empty (OCR might have missed handwritten grade)
                    # Then check next few lines for grade value
                    next_idx = i + 1
                    # Check if line immediately after grade label is empty or a different label
                    if next_idx < len(lines):
                        next_line_immediate = lines[next_idx].strip()
                        # If next line is empty or another label, the grade field was likely blank/not captured
                        is_blank_field = (not next_line_immediate or 
                                         'deadline' in next_line_immediate.lower() or
                                         'march' in next_line_immediate.lower() or
                                         'april' in next_line_immediate.lower() or
                                         'may' in next_line_immediate.lower() or
                                         'june' in next_line_immediate.lower())
                        
                        if is_blank_field:
                            # Grade field appears blank - OCR didn't capture it
                            # We can't infer it, so leave as None
                            logger.info("Grade field appears blank in OCR (not captured)")
                    
                    # Still check next few lines in case grade appears later
                    for j in range(i + 1, min(i + 5, len(lines))):
                        next_line = lines[j].strip()
                        # Skip empty lines, labels, dates
                        if not next_line or 'deadline' in next_line.lower() or 'march' in next_line.lower() or 'april' in next_line.lower() or 'may' in next_line.lower() or 'june' in next_line.lower():
                            continue
                        # Try to extract grade from this line
                        # Look for ordinal: "1st", "1st Grade", "first", etc.
                        ordinal_match = re.search(r'\b(\d+)(?:st|nd|rd|th)\b', next_line.lower())
                        if ordinal_match:
                            grade_int = int(ordinal_match.group(1))
                            if 1 <= grade_int <= 12:
                                normalized["grade"] = grade_int
                                logger.info(f"Fallback: Found grade {grade_int} on line after 'Grade / Grado' label")
                                grade_found = True
                                break
                        # Look for standalone digit 1-12
                        digit_match = re.match(r'^\s*(\d{1,2})\s*$', next_line)
                        if digit_match:
                            grade_int = int(digit_match.group(1))
                            if 1 <= grade_int <= 12:
                                normalized["grade"] = grade_int
                                logger.info(f"Fallback: Found grade {grade_int} as standalone digit after 'Grade / Grado' label")
                                grade_found = True
                                break
                    if grade_found:
                        break
        
        # Note: Removed filename-based name extraction - only extract from PDF document
        
        logger.info(f"{provider.upper()} extraction successful: {sum(1 for v in normalized.values() if v is not None)} fields extracted using {model_name}")
        return normalized
        
    except ImportError as e:
        if "openai" in str(e):
            logger.error("OpenAI package not installed. Run: pip install openai")
            # Try Groq as fallback
            if groq_key:
                logger.info("Falling back to Groq...")
                return extract_fields_llm(contact_block, raw_text)
        logger.error("Required LLM package not installed. Run: pip install openai groq")
        raise RuntimeError("LLM packages not installed. Install with: pip install openai groq")
    
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        # Return all nulls - don't extract name from filename
        return {
            "student_name": None,
            "school_name": None,
            "grade": None,
            "teacher_name": None,
            "city_or_location": None,
            "father_figure_name": None,
            "phone": None,
            "email": None
        }


def extract_fields_hybrid(contact_block: str, raw_text: str = "", return_debug: bool = False) -> dict:
    """
    Hybrid extraction: Try LLM first, fall back to rules if it fails or API key missing.
    
    Args:
        contact_block: Text containing contact information
        raw_text: Full OCR text (optional)
        return_debug: If True, returns (result, debug_info) tuple
        
    Returns:
        dict with extracted fields (or tuple if return_debug=True)
    """
    from pipeline.extract import extract_fields_rules
    
    # Try LLM extraction first
    llm_result = extract_fields_llm(contact_block, raw_text)
    
    # Count how many fields were extracted
    llm_fields_found = sum(1 for v in llm_result.values() if v is not None)
    
    # If LLM found at least 1 required field (name, school, or grade), use it
    # Lowered threshold to see what LLM extracts even if partial
    required_fields = [llm_result.get("student_name"), llm_result.get("school_name"), llm_result.get("grade")]
    required_found = sum(1 for v in required_fields if v is not None)
    
    if required_found >= 1:
        logger.info(f"Using LLM extraction ({llm_fields_found} fields found)")
        if return_debug:
            debug = {
                "extraction_method": "llm",
                "model": "mixtral-8x7b-32768",
                "fields_extracted": llm_fields_found,
                "required_fields_found": {
                    "student_name": llm_result.get("student_name") is not None,
                    "school_name": llm_result.get("school_name") is not None,
                    "grade": llm_result.get("grade") is not None
                },
                "result": llm_result
            }
            return llm_result, debug
        return llm_result
    
    # Otherwise fall back to rule-based
    logger.info("Falling back to rule-based extraction")
    if return_debug:
        result, debug = extract_fields_rules(contact_block, return_debug=True)
        debug["fallback_reason"] = f"LLM found only {required_found}/3 required fields"
        return result, debug
    return extract_fields_rules(contact_block)

