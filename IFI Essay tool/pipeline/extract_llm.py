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


def _extract_unlabeled_header_format(text: str) -> Optional[dict]:
    """
    Extract metadata from essays with unlabeled headers like:
    Line 1: "Student Name Grade"
    Line 2: "School Name"
    Line 3: Essay starts...
    
    Example:
        "Mayra Martinez 6th grade
        Rachel Carson Elementary
        When I'm around my dad..."
    
    Returns:
        Dict with student_name, school_name, grade or None if pattern doesn't match
    """
    if not text or not text.strip():
        logger.info("🔍 Unlabeled header extraction: No text provided")
        return None
        
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    logger.info(f"🔍 Unlabeled header extraction: Found {len(lines)} non-empty lines")
    
    if len(lines) < 2:
        logger.info(f"🔍 Unlabeled header extraction: Not enough lines (need 2+, have {len(lines)})")
        return None
    
    first_line = lines[0]
    second_line = lines[1]
    logger.info(f"🔍 Unlabeled header extraction: Line 1: '{first_line[:100]}'")
    logger.info(f"🔍 Unlabeled header extraction: Line 2: '{second_line[:100]}'")
    
    # Pattern 1: "FirstName LastName Grade" or "FirstName MiddleName LastName Grade"
    # Grade can be: "6th grade", "6th", "grade 6", "Kindergarten", "K", etc.
    grade_pattern = r'\b(\d{1,2}(?:st|nd|rd|th)?(?:\s+grade)?|grade\s+\d{1,2}|kindergarten|kinder|pre-?k|k)\b'
    
    logger.info(f"🔍 Unlabeled header extraction: Searching for grade pattern in line 1")
    grade_match = re.search(grade_pattern, first_line, re.IGNORECASE)
    if grade_match:
        logger.info(f"🔍 Unlabeled header extraction: Found grade match: '{grade_match.group(0)}' at position {grade_match.start()}-{grade_match.end()}")
        grade_text = grade_match.group(0).strip()
        # Extract student name (everything before the grade)
        student_name = first_line[:grade_match.start()].strip()
        
        # Check if student name looks valid (2-4 words, properly capitalized)
        name_words = student_name.split()
        if 2 <= len(name_words) <= 4 and all(w[0].isupper() for w in name_words if w):
            # Check if second line looks like a school name
            school_keywords = ['elementary', 'middle', 'high', 'school', 'academy', 'charter', 'prep', 'center']
            if any(kw in second_line.lower() for kw in school_keywords) or (len(second_line.split()) >= 2 and second_line[0].isupper()):
                # Parse grade to standard format
                grade_parsed = None
                grade_lower = grade_text.lower()
                if 'k' in grade_lower or 'kinder' in grade_lower:
                    grade_parsed = 'K'
                elif 'pre' in grade_lower:
                    grade_parsed = 'Pre-K'
                else:
                    grade_num = re.search(r'\d{1,2}', grade_text)
                    if grade_num:
                        grade_parsed = int(grade_num.group())
                
                logger.info(f"✅ Extracted unlabeled header format: student='{student_name}', school='{second_line}', grade='{grade_parsed}'")
                return {
                    "student_name": student_name,
                    "school_name": second_line,
                    "grade": grade_parsed
                }
            else:
                logger.info(f"🔍 Unlabeled header extraction: Second line doesn't look like a school name")
        else:
            logger.info(f"🔍 Unlabeled header extraction: Student name validation failed - words: {len(name_words)}, capitalized check failed")
    else:
        logger.info(f"🔍 Unlabeled header extraction: No grade pattern found in first line")
    
    return None


def _extract_school_name_fallback(contact_block: str) -> Optional[str]:
    """
    Fallback rule-based extraction for school names when LLM fails.
    
    
    Searches for school name patterns in the contact block:
    - Lines containing school type keywords (Elementary, Middle, High, School, Academy)
    - Lines near "School" or "Escuela" labels (within 5 lines)
    - Capitalized multi-word phrases that look like school names
    
    Args:
        contact_block: Text containing contact information
        
    Returns:
        Extracted school name or None
    """
    lines = contact_block.split('\n')
    
    # School type keywords
    school_type_patterns = [
        r'\b(?:Elementary|Middle|High|School|Academy|Academia|Escuela)\b',
    ]
    
    # Look for school names near "School" or "Escuela" labels
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        
        # Check if this line contains a school label
        if any(label in line_lower for label in ['school', 'escuela']):
            # Check lines before and after the label (within 5 lines)
            search_range = range(max(0, i - 3), min(len(lines), i + 4))
            for j in search_range:
                if j == i:  # Skip the label line itself
                    continue
                    
                candidate_line = lines[j].strip()
                if not candidate_line or len(candidate_line) < 3:
                    continue
                
                # Look for school-type keywords in the candidate line
                if any(re.search(pattern, candidate_line, re.IGNORECASE) for pattern in school_type_patterns):
                    # This looks like a school name
                    # Clean up common OCR artifacts
                    cleaned = re.sub(r'[^\w\s\-&]', '', candidate_line)  # Remove special chars except hyphens and ampersands
                    cleaned = ' '.join(cleaned.split())  # Normalize whitespace
                    if len(cleaned) > 3:  # Must have some content
                        return cleaned
                
                # If no school type keyword, but line looks like a name (capitalized words)
                # and it's near the School label, check if it's likely a school
                if re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+$', candidate_line):
                    # Capitalized multi-word phrase - could be a school name
                    # Only return if it's 2-5 words (typical school name length)
                    words = candidate_line.split()
                    if 2 <= len(words) <= 5:
                        return candidate_line
    
    # Fallback: Look for any line containing school-type keywords anywhere in contact block
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped or len(line_stripped) < 5:
            continue
            
        # Check if line contains school-type keywords
        for pattern in school_type_patterns:
            if re.search(pattern, line_stripped, re.IGNORECASE):
                # Extract the school name (everything on this line, cleaned)
                cleaned = re.sub(r'[^\w\s\-&]', '', line_stripped)
                cleaned = ' '.join(cleaned.split())
                # Must be substantial (not just "School" by itself)
                if len(cleaned) > 8 and 'school' not in cleaned.lower() or len(cleaned.split()) > 1:
                    return cleaned
    
    return None


def _extract_phone_fallback(contact_block: str) -> Optional[str]:
    """
    Fallback rule-based extraction for phone numbers when LLM fails.
    
    Searches for phone number patterns near "Phone" or "Teléfono" labels.
    
    Args:
        contact_block: Text containing contact information
        
    Returns:
        Extracted phone number or None
    """
    lines = contact_block.split('\n')
    
    # Look for phone numbers near "Phone" or "Teléfono" labels
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        
        # Check if this line contains a phone label
        if any(label in line_lower for label in ['phone', 'teléfono', 'telefono', 'tel']):
            # Check same line first (e.g., "Phone: 773-251-0354")
            phone_match = re.search(r'(?:phone|tel[éé]fono|tel)[:\s]+([0-9\s\-\(\)\.]+)', line, re.IGNORECASE)
            if phone_match:
                phone = phone_match.group(1).strip()
                # Clean up phone number (remove spaces, keep digits and common separators)
                phone = re.sub(r'[^\d\-\(\)\.]', '', phone)
                if len(re.sub(r'[^\d]', '', phone)) >= 10:  # Must have at least 10 digits
                    return phone
            
            # Check next few lines for phone number
            for j in range(i + 1, min(i + 3, len(lines))):
                candidate_line = lines[j].strip()
                if not candidate_line:
                    continue
                
                # Look for phone number patterns: digits with optional separators
                phone_patterns = [
                    r'(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})',  # 773-251-0354 or 773.251.0354
                    r'(\(\d{3}\)\s?\d{3}[-.\s]?\d{4})',  # (773) 251-0354
                    r'(\d{10})',  # 7732510354 (10 digits in a row)
                ]
                
                for pattern in phone_patterns:
                    match = re.search(pattern, candidate_line)
                    if match:
                        phone = match.group(1).strip()
                        # Clean up but preserve format
                        if len(re.sub(r'[^\d]', '', phone)) >= 10:
                            return phone
    
    return None


def _extract_email_fallback(contact_block: str) -> Optional[str]:
    """
    Fallback rule-based extraction for email addresses when LLM fails.
    
    Searches for email patterns near "Email" or "Correo" labels.
    
    Args:
        contact_block: Text containing contact information
        
    Returns:
        Extracted email address or None
    """
    lines = contact_block.split('\n')
    
    # Look for email addresses near "Email" or "Correo" labels
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        
        # Check if this line contains an email label
        if any(label in line_lower for label in ['email', 'correo', 'e-mail']):
            # Check same line first (e.g., "Email: user@domain.com")
            email_match = re.search(r'(?:email|correo|e-mail)[:\s]+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', line, re.IGNORECASE)
            if email_match:
                email = email_match.group(1).strip()
                if '@' in email and '.' in email.split('@')[1]:
                    return email
            
            # Check next few lines for email address
            for j in range(i + 1, min(i + 3, len(lines))):
                candidate_line = lines[j].strip()
                if not candidate_line:
                    continue
                
                # Look for email pattern
                email_pattern = r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
                match = re.search(email_pattern, candidate_line)
                if match:
                    email = match.group(1).strip()
                    if '@' in email and '.' in email.split('@')[1]:
                        return email
    
    return None


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
    
    # Try unlabeled header format first (fast, no API calls needed)
    unlabeled_data = _extract_unlabeled_header_format(raw_text or contact_block)
    
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
        
        # Use unlabeled header data as fallback for missing fields
        if unlabeled_data:
            if not normalized.get("student_name") and unlabeled_data.get("student_name"):
                normalized["student_name"] = unlabeled_data["student_name"]
                logger.info(f"Using unlabeled header student_name: {unlabeled_data['student_name']}")
            if not normalized.get("school_name") and unlabeled_data.get("school_name"):
                normalized["school_name"] = unlabeled_data["school_name"]
                logger.info(f"Using unlabeled header school_name: {unlabeled_data['school_name']}")
            if not result.get("grade") and unlabeled_data.get("grade"):
                # Store raw grade for validation below
                result["grade"] = unlabeled_data["grade"]
                logger.info(f"Using unlabeled header grade: {unlabeled_data['grade']}")
        
        # Validate grade is an integer 1-12
        grade_raw = result.get("grade")
        grade_found = False
        if grade_raw is not None:
            try:
                # Handle string inputs like "1st", "first", etc.
                if isinstance(grade_raw, str):
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
        
        # Priority 3 Fix: Enhanced fallback grade extraction with expanded search
        if not grade_found:
            lines = contact_block.split('\n')
            for i, line in enumerate(lines):
                # Check if this line contains grade label
                line_lower = line.lower()
                if ('grade' in line_lower or 'grado' in line_lower):
                    # First, check same line as label for patterns like "Grade: 5" or "Grade 5" or "Grade / Grado: 3"
                    same_line_grade_match = re.search(r'(?:grade|grado)[:\s/]*(\d{1,2})(?:\s|$)', line, re.IGNORECASE)
                    if same_line_grade_match:
                        grade_int = int(same_line_grade_match.group(1))
                        if 1 <= grade_int <= 12:
                            normalized["grade"] = grade_int
                            logger.info(f"Fallback: Found grade {grade_int} on same line as label: '{line.strip()[:50]}'")
                            grade_found = True
                            break
                    
                    # Also check for ordinal on same line: "Grade 1st" or "1st Grade"
                    same_line_ordinal = re.search(r'(?:grade|grado).*?\b(\d+)(?:st|nd|rd|th)\b', line, re.IGNORECASE)
                    if not same_line_ordinal:
                        same_line_ordinal = re.search(r'\b(\d+)(?:st|nd|rd|th)\b.*?(?:grade|grado)', line, re.IGNORECASE)
                    if same_line_ordinal:
                        grade_int = int(same_line_ordinal.group(1))
                        if 1 <= grade_int <= 12:
                            normalized["grade"] = grade_int
                            logger.info(f"Fallback: Found grade {grade_int} (ordinal) on same line as label")
                            grade_found = True
                            break
                    
                    # Check if the next line is blank/empty (OCR might have missed handwritten grade)
                    next_idx = i + 1
                    # Check if lines immediately after grade label are empty or contain other labels
                    blank_field_indicators = []
                    for check_idx in range(next_idx, min(next_idx + 3, len(lines))):
                        check_line = lines[check_idx].strip() if check_idx < len(lines) else ""
                        if not check_line:
                            blank_field_indicators.append(True)
                        elif any(indicator in check_line.lower() for indicator in 
                                ['deadline', 'march', 'april', 'may', 'june', 'july', 'august', 'contest', 'character maximum']):
                            blank_field_indicators.append(True)
                        else:
                            blank_field_indicators.append(False)
                    
                    # If multiple consecutive lines are blank/other labels, grade field is likely blank
                    if len(blank_field_indicators) >= 2 and all(blank_field_indicators[:2]):
                        logger.info("Grade field appears blank in OCR (not captured) - multiple blank lines after label")
                        # Don't break - continue searching in case grade appears elsewhere
                    
                    # Expanded search: Check next 10 lines (increased from 5) for grade value
                    for j in range(i + 1, min(i + 11, len(lines))):
                        next_line = lines[j].strip()
                        # Skip empty lines and label lines
                        if not next_line:
                            continue
                        if any(indicator in next_line.lower() for indicator in 
                              ['deadline', 'march', 'april', 'may', 'june', 'july', 'august', 'contest']):
                            continue
                        
                        # Try to extract grade from this line
                        # Look for ordinal: "1st", "1st Grade", "first", etc.
                        ordinal_match = re.search(r'\b(\d+)(?:st|nd|rd|th)\b', next_line.lower())
                        if ordinal_match:
                            grade_int = int(ordinal_match.group(1))
                            if 1 <= grade_int <= 12:
                                normalized["grade"] = grade_int
                                logger.info(f"Fallback: Found grade {grade_int} (ordinal) on line {j+1} after 'Grade / Grado' label")
                                grade_found = True
                                break
                        
                        # Look for standalone digit 1-12 (must be alone on the line or with minimal text)
                        digit_match = re.match(r'^\s*(\d{1,2})\s*$', next_line)
                        if digit_match:
                            grade_int = int(digit_match.group(1))
                            if 1 <= grade_int <= 12:
                                normalized["grade"] = grade_int
                                logger.info(f"Fallback: Found grade {grade_int} as standalone digit on line {j+1} after 'Grade / Grado' label")
                                grade_found = True
                                break
                        
                        # Also check for "Grade X" or "Xth Grade" patterns on this line
                        grade_on_line = re.search(r'(?:grade|grado)\s*(\d{1,2})', next_line, re.IGNORECASE)
                        if not grade_on_line:
                            grade_on_line = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s*(?:grade|grado)', next_line, re.IGNORECASE)
                        if grade_on_line:
                            grade_int = int(grade_on_line.group(1))
                            if 1 <= grade_int <= 12:
                                normalized["grade"] = grade_int
                                logger.info(f"Fallback: Found grade {grade_int} in 'Grade X' pattern on line {j+1}")
                                grade_found = True
                                break
                    
                    if grade_found:
                        break
        
        # Priority 2 Fix: Fallback school name extraction if LLM didn't find it
        if not normalized.get("school_name") and contact_block:
            school_name_fallback = _extract_school_name_fallback(contact_block)
            if school_name_fallback:
                normalized["school_name"] = school_name_fallback
                logger.info(f"Fallback: Found school name via pattern matching: {school_name_fallback}")
        
        # Fallback phone and email extraction if LLM didn't find them
        if not normalized.get("phone") and contact_block:
            phone_fallback = _extract_phone_fallback(contact_block)
            if phone_fallback:
                normalized["phone"] = phone_fallback
                logger.info(f"Fallback: Found phone via pattern matching: {phone_fallback}")
        
        if not normalized.get("email") and contact_block:
            email_fallback = _extract_email_fallback(contact_block)
            if email_fallback:
                normalized["email"] = email_fallback
                logger.info(f"Fallback: Found email via pattern matching: {email_fallback}")
        
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

