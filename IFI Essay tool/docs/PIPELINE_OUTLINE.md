# IFI Essay Processing Pipeline

## Overview

Submitted PDF/image files go through a 6-step pipeline. Each step feeds into the next. If any step fails, the entire job is marked as **failed** and the error is logged.

```
Upload → Storage → OCR → Segmentation + Extraction → Validation → Database
```

---

## Step 1: Upload & Ingestion (`pipeline/supabase_storage.py`)

- User uploads a PDF or image via the Flask web UI
- File bytes are hashed (SHA-256) to produce a deterministic `submission_id` (first 12 hex chars)
- File is uploaded to Supabase Storage bucket `essay-submissions` at path: `{user_id}/{submission_id}/original.{ext}`
- Uses **service role key** (not user JWT) to avoid token expiry issues in background workers

**Inputs:** raw file bytes, filename, user ID
**Outputs:** `submission_id`, `artifact_dir`, `storage_url`

---

## Step 2: OCR (`pipeline/ocr.py`)

- Converts the uploaded document to text using one of three providers:
  - **Google Cloud Vision** (production) - uses `DOCUMENT_TEXT_DETECTION` for handwriting support
  - **EasyOCR** (alternative) - open-source, local, no API key needed
  - **Stub** (testing) - returns hardcoded sample text
- For PDFs: first page is rendered to PNG at 300 DPI (via PyMuPDF), then sent to OCR
- Computes an OCR quality score (0-1) based on alpha ratio and garbage character ratio

**Inputs:** file path (temp file on disk)
**Outputs:** `OcrResult` (text, confidence_avg, lines)

---

## Step 3: Segmentation (`pipeline/segment.py`)

- Splits the raw OCR text into two blocks:
  - **Contact block** - form fields (name, school, grade, etc.)
  - **Essay block** - the actual essay content
- Uses keyword matching (bilingual: English + Spanish) to detect where the form ends and essay begins
- Handles IFI official forms, free-form essays, and header-metadata formats

**Inputs:** raw OCR text
**Outputs:** `contact_block`, `essay_block`

---

## Step 4: Extraction (`pipeline/extract_ifi.py`, `pipeline/extract.py`)

Two-phase extraction:

### Phase A: LLM Classification & Extraction (`extract_ifi.py`)
- Sends OCR text to Groq (Llama 3.3 70B) or OpenAI (GPT-4o) with a structured prompt
- Classifies document type: `IFI_OFFICIAL_FORM_FILLED`, `ESSAY_WITH_HEADER_METADATA`, `ESSAY_ONLY`, etc.
- Extracts fields: `student_name`, `school_name`, `grade`, `father_figure_name`, `essay_text`, etc.
- Falls back to rule-based extraction if no LLM API key is set

### Phase B: Rule-Based Extraction (`extract.py`)
- Bilingual label matching (English + Spanish) near known field labels
- Strategies: value after colon, value after label text, value on next line
- Grade parsing handles ordinals (1st, 2nd), words (Kindergarten), integers
- Also computes essay metrics: `word_count`, `char_count`, `paragraph_count`

**Inputs:** contact_block, raw OCR text, filename
**Outputs:** structured fields dict + essay metrics

---

## Step 5: Validation (`pipeline/validate.py`)

- Checks required fields: `student_name`, `school_name`, `grade`, `word_count > 0`
- Flags issues: `MISSING_STUDENT_NAME`, `MISSING_GRADE`, `EMPTY_ESSAY`, `SHORT_ESSAY`, `LOW_CONFIDENCE`
- **All records start with `needs_review=True`** - must be manually approved
- Creates a `SubmissionRecord` (Pydantic model) with all extracted data and validation flags

**Inputs:** partial record dict
**Outputs:** `SubmissionRecord`, validation report

---

## Step 6: Database Save (`pipeline/supabase_db.py`)

- Saves the `SubmissionRecord` to Supabase PostgreSQL (`submissions` table)
- Uses upsert on `submission_id` (so re-uploads update rather than duplicate)
- Checks for existing records to detect duplicates and track previous owner
- Uses service role key for authentication (bypasses RLS)

**Inputs:** `SubmissionRecord`, filename, user ID, access token
**Outputs:** success/failure, duplicate info

---

## Orchestration

### Worker Job (`jobs/process_submission.py`)
- Runs in a background worker (Redis + RQ)
- Calls steps 1-6 in sequence
- On success: sends email notification, returns result dict
- On failure: logs error with traceback, sends failure email, **re-raises exception** so RQ marks job as `failed`

### Pipeline Runner (`pipeline/runner.py`)
- Orchestrates steps 2-5 (OCR through validation)
- Writes temporary artifacts (ocr.json, raw_text.txt, essay_block.txt, structured.json, validation.json)
- Cleans up temp directory after processing

---

## Key Data Models (`pipeline/schema.py`)

- **`OcrResult`**: text, confidence_avg, lines
- **`SubmissionRecord`**: submission_id, student_name, school_name, grade, word_count, needs_review, review_reason_codes, artifact_dir

---

## Error Handling

| Failure Point | What Happens |
|---|---|
| Storage upload fails | Exception raised, job marked as failed |
| OCR API error (e.g. bad credentials) | Exception raised, job marked as failed |
| LLM extraction fails (e.g. bad API key) | Falls back to rule-based extraction |
| Validation finds missing fields | Record saved with `needs_review=True` + issue flags |
| Database save fails | Exception raised, job marked as failed |
| Email notification fails | Warning logged, job still succeeds |
