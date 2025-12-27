# OCR Quality Score and Confidence Metrics

## Overview

**Current Stack:**
- **OCR Provider:** Google Cloud Vision API (`DOCUMENT_TEXT_DETECTION`)
- **LLM Provider:** Groq API (`llama-3.3-70b-versatile`)

The `ocr_confidence_avg` value represents OCR output quality. Google Vision API provides confidence scores at symbol, word, paragraph, and page levels, but our current implementation computes a **deterministic quality proxy** based on extracted text characteristics (letter density and symbol noise) rather than extracting native confidence values. 

**Critical:** This score is not a probability of correctness and should not be interpreted as statistical accuracy. It is a heuristic estimate of text cleanliness/readability used exclusively for triage and review prioritization. This score does not replace human review.

**Important:** This score reflects overall OCR text quality. Field extraction confidence is handled separately during LLM extraction (Groq Llama 3.3 70B) and validation (e.g., missing required fields, pattern mismatches). A single global score can be high while one critical field is wrong, which is why all submissions undergo human review regardless of the quality score.

---

## Calculation Methods by Provider

### 1. Google Cloud Vision (Currently Used)

**Provider:** Google Cloud Vision API  
**Feature:** `DOCUMENT_TEXT_DETECTION` (handwriting-optimized)  
**Method:** Deterministic Quality Score (Heuristic-Based Proxy)

**Note:** Google Cloud Vision API's `DOCUMENT_TEXT_DETECTION` feature does provide confidence scores at symbol, word, paragraph, and page levels. However, our current implementation computes a **deterministic quality proxy** based on text characteristics rather than extracting these native confidence values from the API response.

Native confidence values from Google Vision are not consistently exposed across all detected elements and vary by layout and handwriting style, which makes aggregation non-trivial and provider-specific. The quality proxy provides a consistent, deterministic metric that works reliably across all submission types.

This quality score is a heuristic estimate of text cleanliness/readability, not true model confidence. It serves as a consistent metric for prioritizing review and flagging poor OCR output. The quality proxy is reliable for triage purposes, though future enhancements could incorporate Google Vision's native confidence scores for comparison.

#### Formula:

```python
def compute_ocr_quality_score(text: str) -> float:
    # Step 1: Analyze character composition
    non_whitespace_chars = [c for c in text if not c.isspace()]
    
    # Step 2: Calculate ratios
    alpha_ratio = (number of letters) / (total non-whitespace characters)
    garbage_ratio = (non-alphanumeric symbols) / (total non-whitespace characters)
    
    # Step 3: Weighted score
    score = (alpha_ratio * 0.8) + ((1 - garbage_ratio) * 0.2)
    
    # Step 4: Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, score))
```

#### How It Works:

1. **Alpha Ratio (80% weight):**
   - Measures the proportion of actual letters in the text
   - Higher = more readable text
   - Example: "Hello World" = 100% alpha (all letters)
   - Example: "H3ll0 W0r1d" = 54.5% alpha (6 letters / 11 chars)

2. **Garbage Ratio (20% weight):**
   - Measures the proportion of non-alphanumeric characters (punctuation, symbols)
   - **Note:** Digits are considered valid (not garbage) since they're common in addresses, grades, IDs
   - Formula: `garbage_ratio = (non-alphanumeric chars) / (total non-whitespace chars)`
   - Lower = cleaner text
   - Example: "Hello!" = 16% garbage (1 symbol / 6 chars)
   - Example: "H@#$!o" = 66% garbage (4 symbols / 6 chars)
   - Example: "Grade 5" = 0% garbage (digit is alphanumeric, space ignored)

3. **Final Score:**
   - Weighted combination: 80% alpha ratio + 20% (1 - garbage ratio)
   - Ranges from 0.0 (worst) to 1.0 (best)

#### Example Calculation:

```
Text: "Hello World"

Non-whitespace: ['H','e','l','l','o','W','o','r','l','d']
Total: 10
Letters: 10
Alpha ratio: 10/10 = 1.0
Garbage ratio: 0/10 = 0.0

Score = (1.0 * 0.8) + ((1 - 0.0) * 0.2)
      = 0.8 + 0.2
      = 1.0 (100% quality score)
```

```
Text: "H3ll0 W0r1d!" (OCR errors)

Non-whitespace: ['H','3','l','l','0','W','0','r','1','d','!']
Total: 11
Letters: 6
Alpha ratio: 6/11 = 0.545
Alphanumeric: 10 (6 letters + 4 digits)
Garbage ratio: 1/11 = 0.091 (1 symbol: '!')

Score = (0.545 * 0.8) + ((1 - 0.091) * 0.2)
      = 0.436 + 0.182
      = 0.618 (61.8% quality score)
```

**Note:** Digits (3, 0, 1) are counted as alphanumeric, not garbage, since they may be valid parts of addresses, grades, or IDs. Only punctuation and symbols count as garbage.

---

### 2. EasyOCR Provider (Not Currently Used)

**Status:** Available but not used in production  
**Reason:** Lower confidence scores compared to Google Vision for handwriting recognition

EasyOCR is implemented but not used due to lower confidence for handwritten text. If enabled, it would combine native model confidence (70%) with the quality score (30%) for a weighted average.

**Note:** The current production system uses Google Vision exclusively for OCR.

---

---

## LLM Extraction (Field-Level Processing)

**Provider:** Groq API  
**Model:** `llama-3.3-70b-versatile` (70 billion parameters)  
**Purpose:** Structured field extraction from OCR text

While the OCR quality score reflects overall text quality, individual field extraction uses Groq's Llama 3.3 70B model to:
- Extract structured fields (name, school, grade, etc.)
- Correct OCR errors through context understanding
- Handle bilingual content (English/Spanish)
- Infer missing information from context

**Field Extraction Confidence:**
- LLM extraction success is tracked separately (not included in `ocr_confidence_avg`)
- Missing fields trigger `review_reason_codes` (e.g., `MISSING_SCHOOL_NAME`)
- High OCR quality doesn't guarantee complete field extraction
- Low OCR quality may still yield complete fields if LLM can infer context

---

### Stub Provider (Testing Only)

**Method:** Fixed Value

```python
confidence_avg = 0.65  # 65% - typical for handwriting
```

Used only for development/testing when no real OCR provider is configured.

---

## Score Interpretation

| Score Range | Quality | Meaning |
|-------------|---------|---------|
| 0.90 - 1.00 | Excellent | Very clean text, minimal OCR errors, high readability |
| 0.70 - 0.89 | Good | Mostly accurate, minor errors, good readability |
| 0.50 - 0.69 | Fair | Some errors, but readable (typical for handwriting) |
| 0.30 - 0.49 | Poor | Many errors, may need review, lower readability |
| 0.00 - 0.29 | Very Poor | Significant problems, likely needs re-processing |

**Note:** For handwritten submissions, scores in the 0.50-0.70 range are normal and expected, as handwriting inherently produces more variable text quality than typed text.

---

## Validation Thresholds

The system uses confidence scores for validation:

```python
# Low confidence flag
if ocr_confidence_avg < 0.5:  # 50%
    review_reason_codes.append("LOW_CONFIDENCE")
```

**Review Flag:**
- Scores below **0.5 (50%)** trigger `LOW_CONFIDENCE` flag
- These records require manual review to verify accuracy
- Low confidence often indicates:
  - Poor handwriting quality
  - Image quality issues
  - OCR processing errors

---

## Code Location

**Main Calculation Function:**
- `pipeline/ocr.py` → `compute_ocr_quality_score(text: str) -> float`

**Provider Implementations:**
- `GoogleVisionOcrProvider.process_image()` → Uses quality score directly (currently used)
- `EasyOcrProvider.process_image()` → Available but not used (lower confidence)
- `StubOcrProvider.process_image()` → Returns fixed 0.65 (testing only)

**LLM Provider:**
- `extract_ifi.py` → Groq API with `llama-3.3-70b-versatile` model
- Handles field extraction after OCR processing

**Storage:**
- Stored in database as `ocr_confidence_avg` (REAL type)
- Displayed in UI as percentage (e.g., "OCR Confidence: 65.00%")
- Exported to CSV with 2 decimal places
- LLM extraction metadata (including model used) stored in `extraction_debug.json` artifacts

---

## Limitations

1. **Quality Proxy vs. True Confidence (Google Vision):**
   - Current implementation: Heuristic quality score, not actual OCR model confidence
   - Google Vision API does provide confidence scores, but native confidence values are not consistently exposed across all detected elements and vary by layout and handwriting style
   - Aggregation of native confidence would be non-trivial and provider-specific
   - Quality score estimates text cleanliness/readability, not statistical accuracy or probability of correctness
   - May not perfectly reflect true OCR accuracy
   - Internally, `ocr_confidence_avg` represents a quality score, not true confidence

2. **Provider-Specific:**
   - Google Vision: Deterministic quality proxy (0-1)
   - EasyOCR: Not used in production (lower confidence for handwriting)
   - Quality proxy provides consistent scoring regardless of provider

3. **Handwriting Challenges:**
   - Handwritten text typically scores 0.50-0.70
   - Even "good" handwriting may score lower than typed text
   - Normal for handwritten submissions

4. **Global vs. Field-Level:**
   - Score reflects overall text quality, not individual field accuracy
   - A high global score doesn't guarantee all fields are correct
   - Individual field validation uses separate logic (pattern matching, LLM extraction, review flags)

---

## Best Practices

1. **Use Quality Score for Triage, Not Approval:**
   - Flag records < 50% for prioritized manual review
   - Use as one signal among many (missing fields, pattern mismatches, etc.)
   - **Never auto-approve based solely on quality score**

2. **Combine with Other Indicators:**
   - Low quality score + missing fields = high priority review
   - Low quality score + complete extraction = verify accuracy
   - High quality score + missing fields = still needs review

3. **Business-Safe Interpretation:**
   - "Across the current submission set, OCR output quality averages ~0.93 on a heuristic quality scale. All submissions still undergo human review; the score is used to guide reviewer attention and to flag unusually poor OCR output for deeper inspection."
   - Never say "X% confidence" without "quality" nearby (e.g., "93% quality score", not "93% confidence")
   - Avoid implying statistical accuracy or guaranteed correctness
   - Emphasize that the score aids triage, not approval
   - Internally, `ocr_confidence_avg` represents an OCR quality score rather than true model confidence

4. **Audit Trail:**
   - All outputs are auditable via artifacts (original PDF, OCR JSON, extracted text)
   - Quality score is one metric among many for quality assessment

---

## Example Artifact Output

**ocr.json:**
```json
{
  "text": "Name: John Doe\nSchool: Lincoln Elementary\n...",
  "confidence_avg": 0.67,
  "lines": [
    "Name: John Doe",
    "School: Lincoln Elementary",
    ...
  ]
}
```

**Validation Result:**
- `ocr_confidence_avg: 0.67` = 67% quality score
- Above 50% threshold = No `LOW_CONFIDENCE` flag
- Good overall text quality, but individual fields still require verification

---

---

## Future Enhancement: Google Vision Native Confidence

**Current State:** We compute a heuristic quality proxy for Google Vision.

**Potential Improvement:** Google Cloud Vision API's `DOCUMENT_TEXT_DETECTION` returns confidence scores at multiple levels:
- Symbol-level confidence (per character)
- Word-level confidence (per word)
- Paragraph-level confidence
- Page-level confidence

These could be extracted and aggregated (e.g., weighted average of word-level confidences) to provide true model confidence alongside the quality proxy. This would enable:
- Comparison between quality proxy and actual model confidence
- More accurate confidence-based flagging
- Validation of quality proxy accuracy against native confidence

**Implementation Note:** This would require parsing `response.full_text_annotation.pages[].blocks[].paragraphs[].words[].confidence` from the Vision API response. The quality proxy currently serves well for triage purposes, but native confidence extraction would provide additional validation signals.

---

---

## Current System Configuration

**OCR Stack:**
- Provider: Google Cloud Vision API
- Feature: `DOCUMENT_TEXT_DETECTION`
- Confidence: Quality proxy (heuristic-based)

**LLM Stack:**
- Provider: Groq API
- Model: `llama-3.3-70b-versatile` (70B parameters)
- Purpose: Field extraction and OCR error correction

**Processing Flow:**
1. Google Vision extracts text → Quality score computed
2. Groq Llama 3.3 70B extracts structured fields from OCR text
3. Validation flags records needing review (low quality, missing fields)

---

## Business-Safe Summary

The system computes an OCR quality score that estimates the cleanliness and readability of extracted text. For Google Vision OCR, this score is a deterministic heuristic based on letter density and symbol noise, not a statistical confidence value. The score is used exclusively for triage and review prioritization. All submissions undergo human review regardless of score. Structured field extraction and validation are handled separately using an LLM (Groq Llama 3.3 70B) and rule-based checks, ensuring that no record is finalized automatically.

**Key Points:**
- Quality score is a heuristic, not a probability of correctness
- All submissions require human review
- Score guides attention, never auto-approves
- Field extraction and validation are separate layers
- Full audit trail via artifacts for every submission

---

**Last Updated:** December 2024  
**Location:** 
- OCR: `pipeline/ocr.py` → `compute_ocr_quality_score()`
- LLM: `pipeline/extract_ifi.py` → Groq `llama-3.3-70b-versatile`  
**Status:** Google Vision uses quality proxy; Groq handles field extraction  
**Field Name:** `ocr_confidence_avg` (represents quality score, not true confidence)

