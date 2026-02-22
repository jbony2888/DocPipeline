# Extraction Error Analysis Report
**Date:** December 24, 2025  
**Total Records Analyzed:** 10  
**Records Needing Review:** 10 (100%)

## Executive Summary

This report analyzes extraction errors and missing fields in the IFI Essay Gateway processing pipeline. The analysis reveals three critical issues affecting data extraction quality:

1. **Essay Segmentation Failure** (50% of records) - Essay text is not being properly extracted, resulting in `word_count: 0`
2. **Missing School Name** (70% of records) - School names are not being extracted even when present in OCR text
3. **Missing Grade** (70% of records) - Grade values are not being extracted despite fallback logic

## Error Breakdown by Reason Code

| Reason Code | Count | Percentage | Description |
|------------|-------|------------|-------------|
| `EMPTY_ESSAY` | 5 | 50% | Essay text not extracted, word_count = 0 |
| `MISSING_SCHOOL_NAME` | 7 | 70% | School name field is null |
| `MISSING_GRADE` | 7 | 70% | Grade field is null |
| `MISSING_STUDENT_NAME` | 1 | 10% | Student name field is null |
| `SHORT_ESSAY` | 1 | 10% | Essay has < 50 words |

**Note:** Many records have multiple reason codes (e.g., a record can be missing both school name AND grade).

## Root Cause Analysis

### 1. Essay Segmentation Failure (`EMPTY_ESSAY` - 50% of records)

**Problem:** The `split_contact_vs_essay()` function in `pipeline/segment.py` is failing to properly separate essay content from form metadata, resulting in empty or truncated `essay_block.txt` files.

**Evidence:**
- Record `3f3f39b6965b` (Francely Pacheco): `raw_text.txt` contains a 283-word essay, but `essay_block.txt` is completely empty
- Record `aea75873e3bd` (Valerie Pantoja): `essay_block.txt` only contains the final 6 lines of text, missing the majority of the essay
- Record `3b9bcbc975e8`: Essay content exists in `contact_block.txt` but not in `essay_block.txt`

**Root Causes:**
1. **Heuristic-based segmentation is unreliable:** The function uses keyword matching and line-length heuristics that don't account for:
   - Essays that start immediately after form fields without clear markers
   - OCR errors that corrupt segmentation markers
   - Bilingual forms with varying layouts
   - Handwritten text that may not follow expected patterns

2. **Prompt text confusion:** The essay prompt text (`"What My Father or an Important Father-Figure* Means to Me"`) appears in both contact and essay sections, causing the algorithm to miscategorize content.

3. **Conservative contact_end_idx:** The function enforces a minimum `contact_end_idx = 10`, which may be cutting off early essay content.

**Impact:** 
- `word_count` is always 0 when essay_block is empty, triggering `EMPTY_ESSAY` validation error
- Essays cannot be reviewed or analyzed
- All records with empty essays must be manually reviewed

---

### 2. Missing School Name (`MISSING_SCHOOL_NAME` - 70% of records)

**Problem:** The LLM extraction (Groq `llama-3.3-70b-versatile`) is not extracting school names even when they appear in the OCR text.

**Evidence:**
- Record `3f3f39b6965b` (Francely Pacheco): The `_ifi_metadata.notes` explicitly states: "No school or grade information present in the document"
- However, examination of the OCR text shows school information may be present but not in expected locations
- The LLM prompt instructs to look for school names "right BEFORE the 'School' label", but OCR may have misaligned text

**Root Causes:**
1. **OCR text alignment issues:** Google Vision OCR may place school names on unexpected lines relative to the "School / Escuela" label, especially with handwritten forms.

2. **Prompt specificity:** The LLM prompt (in `extract_llm.py` lines 121-132) emphasizes checking the line "IMMEDIATELY BEFORE" the School label, but OCR may:
   - Place the label and value on the same line
   - Have blank lines between label and value
   - Have OCR errors in the label itself (e.g., "Scho0l" instead of "School")

3. **No fallback extraction:** Unlike grade extraction (which has fallback rule-based logic), school name extraction has no fallback mechanism when the LLM fails.

4. **Blank form fields:** Some forms may genuinely not have school names filled in by students.

**Impact:**
- 70% of records require manual school name entry
- School-based statistics and filtering cannot be automated
- Volunteers must manually review and update school information

---

### 3. Missing Grade (`MISSING_GRADE` - 70% of records)

**Problem:** Grade values are not being extracted despite having both LLM extraction and fallback rule-based logic.

**Evidence:**
- Record `3f3f39b6965b` (Francely Pacheco): Grade is null even though the form appears to have grade information
- The fallback logic in `extract_llm.py` (lines 321-374) attempts to parse grades from lines after "Grade / Grado", but it's still failing

**Root Causes:**
1. **Blank grade fields:** Students may not have filled in the grade field on the form, making extraction impossible.

2. **OCR missed handwritten grades:** Handwritten grade values (especially if written in cursive or small text) may not be captured by OCR at all. The code attempts to detect this (lines 333-346) but may not handle all edge cases.

3. **Grade format variations:** While the code handles ordinals ("1st", "2nd") and words ("first", "primero"), it may miss:
   - Grades written as "Grade 5" on the same line as the label
   - Grades with OCR errors (e.g., "7" read as "7" but on wrong line)
   - Grades written in unexpected locations

4. **LLM prompt priority order:** The prompt instructs the LLM to check the line "IMMEDIATELY AFTER" the grade label first, but if that line is blank or contains "Deadline:", it returns null. The fallback logic may not be robust enough.

**Impact:**
- 70% of records require manual grade entry
- Grade-based sorting and filtering cannot be automated
- Contest eligibility by grade level cannot be verified automatically

---

### 4. Missing Student Name (`MISSING_STUDENT_NAME` - 10% of records)

**Problem:** Only 1 out of 10 records is missing student name, suggesting this field is generally working well.

**Evidence:**
- Record `3b9bcbc975e8`: Student name is null
- The `contact_block.txt` shows "Student's Name" label but no value after it
- This appears to be a genuinely blank form field (student didn't fill it in) or an essay-only document (no form metadata)

**Root Cause:**
- Likely a genuinely blank field rather than an extraction failure
- The file name suggests this may be an essay-only submission: `Maritza-Medrano-2022-IFI-Fatherhood-Essay-Contest.pdf`
- The LLM correctly identified this as `ESSAY_WITH_HEADER_METADATA` doc_type with no student metadata

**Impact:** Low - only affects 10% of records

---

### 5. Word Count Discrepancy (`word_count: 0` vs. Actual Essay Content)

**Problem:** `structured.json` shows `word_count: 0` for records that clearly have essay content in `raw_text.txt`.

**Evidence:**
- Record `3f3f39b6965b`: `raw_text.txt` contains a 283-word essay, but `structured.json.word_count = 0`
- Record `aea75873e3bd`: Essay content exists but `word_count = 0`

**Root Cause:**
- `compute_essay_metrics()` in `extract.py` (line 489) counts words from `essay_block`, not `raw_text`
- Since `essay_block` is empty (due to segmentation failure), word count is always 0

**Impact:**
- All records with segmentation failures are incorrectly flagged as `EMPTY_ESSAY`
- Word count statistics are inaccurate
- Short essay detection (`< 50 words`) cannot work correctly

---

## Case Studies

### Case Study 1: Record `3f3f39b6965b` (Francely Pacheco)

**Issues:**
- ✅ Student name extracted: "Francely Pacheco"
- ❌ School name: null
- ❌ Grade: null  
- ❌ Word count: 0 (but essay clearly exists in `raw_text.txt`)

**Analysis:**
- The form is classified as `IFI_OFFICIAL_FORM_FILLED`
- The LLM found the student name but missed school and grade
- The `essay_block.txt` is completely empty, causing `word_count = 0`
- The `raw_text.txt` shows a complete essay starting at line 6

**Why school/grade missing:**
- The LLM notes state: "No school or grade information present in the document"
- This could mean:
  1. The fields were genuinely blank on the form
  2. OCR missed the handwritten school/grade values
  3. The values were written in a location the LLM didn't check

### Case Study 2: Record `aea75873e3bd` (Valerie Pantoja)

**Issues:**
- ✅ Student name extracted: "Valerie Pantoja"
- ✅ School name extracted: "Edwards"
- ✅ Grade extracted: 2
- ❌ Word count: 0 (essay_block only has 6 lines)

**Analysis:**
- This record shows that when segmentation partially works, metadata can be extracted correctly
- However, the essay is truncated - only the last 6 lines appear in `essay_block.txt`
- The `contact_block.txt` likely contains the majority of the essay content

**Why essay truncated:**
- The segmentation algorithm likely confused the essay content with form metadata
- The essay may have started earlier than the algorithm detected

### Case Study 3: Record `3b9bcbc975e8` (No Name)

**Issues:**
- ❌ Student name: null
- ❌ School name: null
- ❌ Grade: null
- ✅ Word count: 153 (essay exists but is off-prompt)

**Analysis:**
- Document type: `ESSAY_WITH_HEADER_METADATA`
- Essay is about the mother, not a father figure (`is_off_prompt: true`)
- No student metadata in the document header
- The LLM correctly identified this as an essay-only document with no form fields

**Why no metadata:**
- This appears to be a typed essay submission without the official form
- The filename suggests it's a 2022 contest entry that may have been submitted in a different format

---

## Recommendations for Improvement

### Priority 1: Fix Essay Segmentation (Critical - affects 50% of records)

**Problem:** Essay text is not being extracted, causing `word_count = 0` and `EMPTY_ESSAY` errors.

**Recommendations:**

1. **Improve segmentation heuristics:**
   - Use the IFI LLM classification result (`doc_type`) to inform segmentation
   - For `IFI_OFFICIAL_FORM_FILLED`, look for the essay prompt text (`"What My Father..."`) and extract everything after it until "reaction" markers
   - For `ESSAY_WITH_HEADER_METADATA`, parse the first 1-4 lines as metadata, then extract the rest as essay
   - Use the LLM-extracted `essay_text` from `_ifi_metadata` as the primary source instead of relying solely on heuristics

2. **Fallback to LLM-extracted essay text:**
   - Modify `runner.py` to check if `_ifi_metadata.essay_text` exists and use it as the essay block if segmentation fails
   - Update `compute_essay_metrics()` to use `_ifi_metadata.essay_text` if `essay_block` is empty

3. **Add essay validation in segmentation:**
   - After segmentation, validate that `essay_block` contains substantial text (e.g., > 50 words)
   - If not, try alternative segmentation strategies or use the full `raw_text` minus known form labels

**Implementation:**
```python
# In runner.py, after extraction:
ifi_metadata = contact_fields.get("_ifi_metadata", {})
llm_essay_text = ifi_metadata.get("essay_text")

# If segmentation failed (essay_block is too short) but LLM found essay text, use LLM version
if len(essay_block.split()) < 50 and llm_essay_text and len(llm_essay_text.split()) > 50:
    essay_block = llm_essay_text
    # Re-segment using LLM essay as guide
```

**Expected Impact:** 
- Reduce `EMPTY_ESSAY` errors from 50% to < 10%
- Enable accurate word count calculation
- Allow automated essay content review

---

### Priority 2: Improve School Name Extraction (High - affects 70% of records)

**Problem:** School names are not being extracted reliably, requiring manual entry.

**Recommendations:**

1. **Expand LLM prompt search strategy:**
   - Don't only check the line "IMMEDIATELY BEFORE" the School label
   - Check the same line as the label (if label is "School: XYZ")
   - Check 2-3 lines before and after the label
   - Look for school name patterns anywhere in the contact block (words like "Elementary", "Middle", "High", "School", "Academy")

2. **Add fallback rule-based extraction:**
   - After LLM extraction fails, search the contact block for common school patterns:
     - Lines containing "Elementary", "Middle School", "High School", "Academy"
     - Lines near the "School" label (within 5 lines)
     - Capitalized multi-word phrases that look like school names

3. **Use OCR confidence scores:**
   - If OCR confidence is low around the School label, try fuzzy matching for the label itself
   - Handle OCR errors in labels (e.g., "Scho0l" → "School")

**Implementation:**
```python
# Add to extract_llm.py after LLM extraction:
if not normalized.get("school_name"):
    # Fallback: Search contact_block for school patterns
    school_patterns = [
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Elementary|Middle|High|School|Academy))\b',
        r'(?:School|Escuela)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
    ]
    for pattern in school_patterns:
        match = re.search(pattern, contact_block, re.IGNORECASE)
        if match:
            normalized["school_name"] = match.group(1).strip()
            logger.info(f"Fallback: Found school name via pattern matching: {normalized['school_name']}")
            break
```

**Expected Impact:**
- Reduce `MISSING_SCHOOL_NAME` errors from 70% to < 30%
- Reduce manual data entry workload

---

### Priority 3: Improve Grade Extraction (High - affects 70% of records)

**Problem:** Grade values are not being extracted despite fallback logic.

**Recommendations:**

1. **Enhance fallback grade extraction:**
   - Expand the search window from 5 lines to 10 lines after "Grade / Grado"
   - Search the entire contact block for standalone digits 1-12, not just after the label
   - Use OCR bounding box information (if available) to find text near the grade label spatially

2. **Improve blank field detection:**
   - The current logic detects blank fields if the next line contains "Deadline:" or dates
   - Also check if the next few lines are completely empty (not just one line)
   - If blank, mark as null rather than attempting further extraction

3. **Handle grade on same line as label:**
   - Check for patterns like "Grade / Grado: 5" or "Grade 5" on the same line
   - Extract grade even if label and value are combined

4. **Use IFI metadata essay context:**
   - If the essay mentions grade level (e.g., "I'm in 3rd grade"), extract it as a hint
   - This is lower confidence but better than null

**Implementation:**
```python
# Enhance fallback in extract_llm.py:
# After checking immediate line, search wider:
for j in range(i + 1, min(i + 10, len(lines))):  # Expand from 5 to 10 lines
    next_line = lines[j].strip()
    # ... existing logic ...
    
# Also check same line as label:
if 'grade' in line_lower or 'grado' in line_lower:
    # Extract grade from same line: "Grade / Grado: 5" or "Grade 5"
    same_line_grade = re.search(r'(?:grade|grado)[:\s/]*(\d{1,2})', line, re.IGNORECASE)
    if same_line_grade:
        grade_int = int(same_line_grade.group(1))
        if 1 <= grade_int <= 12:
            normalized["grade"] = grade_int
            break
```

**Expected Impact:**
- Reduce `MISSING_GRADE` errors from 70% to < 40%
- Note: Some forms may genuinely have blank grade fields, so 100% extraction is unlikely

---

### Priority 4: Improve Word Count Calculation (Medium)

**Problem:** Word count is 0 when essay_block is empty, even if essay content exists elsewhere.

**Recommendations:**

1. **Multi-source word count:**
   - Calculate word count from `essay_block`, `_ifi_metadata.essay_text`, and `raw_text` (minus form labels)
   - Use the highest non-zero value
   - Log which source was used for debugging

2. **Fallback to raw_text analysis:**
   - If `essay_block` is empty, attempt to extract essay from `raw_text` by removing known form labels
   - Use the LLM classification to identify essay boundaries

**Implementation:**
```python
# In runner.py, after extraction:
def get_best_essay_text(essay_block, ifi_metadata, raw_text):
    """Get essay text from best available source."""
    sources = [
        ("essay_block", essay_block),
        ("llm_essay_text", ifi_metadata.get("essay_text", "")),
        ("raw_text_fallback", extract_essay_from_raw(raw_text, ifi_metadata))
    ]
    
    # Return the source with most words
    best_source = max(sources, key=lambda x: len(x[1].split()))
    return best_source[1], best_source[0]

essay_text, source = get_best_essay_text(essay_block, ifi_metadata, ocr_result.text)
essay_metrics = compute_essay_metrics(essay_text)
essay_metrics["source"] = source  # For debugging
```

**Expected Impact:**
- Eliminate false `EMPTY_ESSAY` errors when essay content exists
- Provide accurate word counts for all records with essay content

---

### Priority 5: Enhanced Error Reporting (Low)

**Problem:** Current error codes don't provide enough context for volunteers to fix issues quickly.

**Recommendations:**

1. **Add detailed extraction notes to review reasons:**
   - Include OCR confidence scores in review reasons
   - Note which extraction method was used (LLM vs. fallback)
   - Include hints about where fields might be located (e.g., "Grade field appears blank in OCR")

2. **Create extraction confidence scores:**
   - Assign confidence scores (0-100) to each extracted field
   - Low confidence fields (< 70) should be flagged for review even if extracted

3. **Provide extraction hints in UI:**
   - When a field is missing, show volunteers what the OCR text contained near the expected label
   - Highlight potential matches (e.g., "Found 'Lnc0ln Elementary' near 'School' label - might be the school name")

**Implementation:**
- Modify `validate.py` to include extraction confidence in `review_reason_codes`
- Add a new field `extraction_hints` to `SubmissionRecord` schema
- Display hints in the review UI

**Expected Impact:**
- Reduce time volunteers spend searching for missing information
- Improve data quality by providing context for manual corrections

---

## Testing Recommendations

To validate improvements, create a test suite with:

1. **Segmentation Test Cases:**
   - Forms with essays starting immediately after prompts
   - Bilingual forms with varying layouts
   - Forms with OCR errors in segmentation markers
   - Essay-only documents

2. **Extraction Test Cases:**
   - School names on same line as label
   - School names 2-3 lines away from label
   - Grades written as ordinals ("1st", "first")
   - Grades on same line as label
   - Blank grade fields (should return null, not guess)

3. **Edge Cases:**
   - Blank forms (no student data)
   - Off-prompt essays (about mother, not father)
   - Multi-entry documents
   - Poor quality scans (low OCR confidence)

---

## Conclusion

The analysis reveals that **essay segmentation failure is the most critical issue**, affecting 50% of records and causing cascading problems (incorrect word counts, false `EMPTY_ESSAY` errors). School and grade extraction failures are also significant, affecting 70% of records each.

**Priority Order:**
1. ✅ **Fix essay segmentation** (Critical - affects word count and essay review)
2. ✅ **Improve school name extraction** (High - 70% manual entry required)
3. ✅ **Improve grade extraction** (High - 70% manual entry required)
4. ⚠️ **Enhance word count calculation** (Medium - supports Priority 1)
5. ⚠️ **Better error reporting** (Low - improves volunteer experience)

Addressing these issues will significantly reduce the manual review workload and improve the accuracy of automated processing.

