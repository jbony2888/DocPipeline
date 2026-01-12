# Gateway Scope 1 - Baseline Documentation

**Version:** 1.0  
**Date:** 2024  
**Status:** Current Implementation (Locked Baseline)

## Overview

This document captures the Scope 1 baseline implementation of the IFI Essay Gateway as currently deployed. Scope 1 focuses on the core intake workflow: uploading entry forms, extracting basic information, flagging issues, and exporting to CSV. This baseline does not include scoring, reader workflows, or administrative roles.

## Architecture

### Application Entry Point

- **Frontend/Backend**: Single Streamlit application (`app.py`)
- **UI Framework**: Streamlit (web-based interface)
- **Database**: SQLite (`submissions.db`) for record storage
- **Artifact Storage**: File system (`artifacts/` directory)

### Processing Pipeline

The pipeline consists of the following stages:

1. **Ingestion** (`pipeline/ingest.py`)
2. **OCR** (`pipeline/ocr.py`)
3. **Segmentation** (`pipeline/segment.py`)
4. **Extraction** (`pipeline/extract_ifi.py`)
5. **Validation** (`pipeline/validate.py`)
6. **Storage** (`pipeline/database.py`)
7. **Export** (`pipeline/csv_writer.py`)

## Upload Workflow

### Single Upload

- **UI Component**: Single file uploader widget (Streamlit `st.file_uploader`)
- **Trigger**: User selects "Single Entry" mode
- **Processing**: 
  - File uploaded via `st.file_uploader` (single file)
  - On "Process Entries" button click, calls `ingest_upload()` then `process_submission()`
  - Results displayed immediately after processing
- **Code Location**: `app.py` lines 201-208, 234-292

### Bulk Upload

- **UI Component**: Multiple file uploader widget (`accept_multiple_files=True`)
- **Trigger**: User selects "Multiple Entries" mode
- **Processing**:
  - Multiple files uploaded via `st.file_uploader` (multiple files)
  - Each file processed sequentially in a loop
  - Progress bar shows processing status
  - Summary table displayed after all files processed
- **Code Location**: `app.py` lines 210-218, 236-361

### Upload Implementation Details

- **Function**: `ingest_upload()` in `pipeline/ingest.py`
- **Deterministic IDs**: Submission IDs generated from SHA256 hash of file contents (first 12 characters)
- **Artifact Storage**: Each submission gets a unique directory: `artifacts/{submission_id}/`
- **File Preservation**: Original file saved as `original.{ext}` in artifact directory
- **Metadata**: `metadata.json` created with submission details

## Supported File Types

The application accepts the following file formats:

- **PDF** (`.pdf`)
- **Images**: PNG (`.png`), JPG (`.jpg`), JPEG (`.jpeg`)

**Code Location**: `app.py` lines 204, 212 (`type=["png", "jpg", "jpeg", "pdf"]`)

### File Type Support Notes

- **PDF Processing**: First page is processed (Google Vision OCR)
- **Scanned Documents**: Supported via Google Cloud Vision OCR
- **Handwritten Text**: Supported via Google Cloud Vision OCR (with optional Groq enhancement)

## Extracted Fields

### Required Fields (Scope 1)

The following fields are extracted and considered required for clean records:

1. **student_name** (string | null)
   - Extracted from form labels ("Student's Name / Nombre del Estudiante") or header metadata
   - OCR error correction applied (e.g., "Alv4rez" → "Alvarez")
   - **Code Location**: `pipeline/extract_ifi.py` (LLM extraction)

2. **school_name** (string | null)
   - Extracted from form labels ("School / Escuela") or header lines
   - **Code Location**: `pipeline/extract_ifi.py` (LLM extraction)

3. **grade** (integer 1-12 | string "K" | null)
   - Extracted from form labels ("Grade / Grado")
   - Normalized from ordinal text ("1st", "2nd", etc.) or numeric format
   - Supports Kindergarten as "K"
   - **Code Location**: `pipeline/extract_ifi.py` (`_normalize_grade()` function)

### Optional Fields (Also Extracted)

The following fields are extracted but not required:

- **teacher_name** (string | null)
- **city_or_location** (string | null)
- **father_figure_name** (string | null)
- **phone** (string | null)
- **email** (string | null)

### Extraction Method

- **Primary**: Two-phase LLM extraction (`pipeline/extract_ifi.py`)
  - Phase 1: Document classification (IFI official form, blank template, essay-only, etc.)
  - Phase 2: Field extraction based on classification
  - LLM Providers: OpenAI GPT-4o (if `OPENAI_API_KEY` set) or Groq (if `GROQ_API_KEY` set)
- **Fallback**: Basic heuristics if no LLM API keys available
- **Code Location**: `pipeline/extract_ifi.py` (`extract_fields_ifi()` function)

## Flagging Behavior

### Missing/Ambiguous Data Flagging

All records start with `needs_review=True` by default. The validation module flags records with the following conditions:

**Flag Codes** (stored in `review_reason_codes`, semicolon-separated):

- `MISSING_STUDENT_NAME`: Student name not found
- `MISSING_SCHOOL_NAME`: School name not found
- `MISSING_GRADE`: Grade not found
- `EMPTY_ESSAY`: Essay word count is 0
- `SHORT_ESSAY`: Essay word count < 50 words
- `LOW_CONFIDENCE`: OCR confidence < 50% (if available)
- `PENDING_REVIEW`: Record has no issues but still requires manual review (default state)

**Validation Logic**:
- **Code Location**: `pipeline/validate.py` (`validate_record()` function)
- All records require manual approval before being marked as "clean"
- Records are routed to `submissions_needs_review.csv` if `needs_review=True`
- Records are routed to `submissions_clean.csv` if `needs_review=False` (after manual approval)

### Flagging Implementation

- **Function**: `validate_record()` in `pipeline/validate.py`
- **Default State**: All records start with `needs_review=True`
- **Manual Approval**: Users can manually approve records via UI ("Approve & Move to Clean" button)
- **UI Display**: Review reasons formatted for display in `app.py` (`format_review_reasons()` function, lines 40-64)

## Grade Grouping Behavior

**Current Implementation**: Grade grouping is **not implemented** in the codebase.

- **UI Text**: The application description mentions "sorts essays by grade level" (`app.py` line 101)
- **Database Queries**: Records are ordered by `created_at DESC` (newest first), not by grade
- **CSV Export**: CSV files are not sorted or grouped by grade
- **Database Schema**: Grade is stored as `INTEGER` but no grouping/sorting by grade exists

**Note**: This is mentioned in the UI description but the functionality is not implemented in Scope 1. Records are simply stored and exported in chronological order.

## Export Format

### CSV Export

Records are exported to CSV files in the `outputs/` directory:

- **Clean Records**: `outputs/submissions_clean.csv`
- **Needs Review Records**: `outputs/submissions_needs_review.csv`

### CSV File Format

**Headers** (frozen, defined in `pipeline/csv_writer.py`):
```csv
submission_id,student_name,school_name,grade,teacher_name,city_or_location,father_figure_name,phone,email,word_count,ocr_confidence_avg,review_reason_codes,artifact_dir
```

**Field Details**:
- `submission_id`: Unique 12-character identifier (SHA256 hash prefix)
- `student_name`, `school_name`, etc.: Extracted field values (empty string if null)
- `grade`: Integer (1-12) or empty string if null
- `word_count`: Integer count of essay words
- `ocr_confidence_avg`: Float as string (formatted to 2 decimal places) or empty string
- `review_reason_codes`: Semicolon-separated flag codes (e.g., "MISSING_STUDENT_NAME;SHORT_ESSAY")
- `artifact_dir`: Path to artifact directory (e.g., "artifacts/094befe74871")

### Export Implementation

- **Function**: `append_to_csv()` in `pipeline/csv_writer.py`
- **Routing**: Records routed based on `needs_review` flag
- **File Creation**: CSV files created with headers if they don't exist
- **Encoding**: UTF-8 encoding
- **UI Trigger**: "Write to CSV" button (single) or "Export All to CSV" button (bulk)

### Database Storage

In addition to CSV export, all records are automatically saved to SQLite database:

- **Database File**: `submissions.db` (or `/app/data/submissions.db` in Docker)
- **Table**: `submissions`
- **Auto-save**: Records saved immediately after processing (before CSV export)
- **Code Location**: `pipeline/database.py`, `app.py` line 268 (`save_record()`)

## Explicit Out-of-Scope (Scope 1)

The following features are **explicitly out of scope** for Scope 1:

1. **Scoring/Evaluation**: No essay scoring, rating, or evaluation functionality
2. **Reader Workflow**: No reader assignment, reader interface, or reading workflow
3. **Administrative Roles**: No role-based access control, user management, or permissions
4. **Grade Grouping/Sorting**: No automatic grouping or sorting by grade level (despite UI mention)
5. **Essay Content Analysis**: No analysis of essay content beyond word count
6. **Automated Approval**: All records require manual review/approval (no auto-approval logic)

## Code Locations Summary

| Component | File Path | Key Functions |
|-----------|-----------|---------------|
| Main Application | `app.py` | UI, upload handlers, processing orchestration |
| Upload/Ingestion | `pipeline/ingest.py` | `ingest_upload()` |
| OCR | `pipeline/ocr.py` | `get_ocr_provider()`, Google Vision provider |
| Segmentation | `pipeline/segment.py` | `split_contact_vs_essay()` |
| Extraction | `pipeline/extract_ifi.py` | `extract_fields_ifi()`, `extract_ifi_submission()` |
| Validation | `pipeline/validate.py` | `validate_record()` |
| Database | `pipeline/database.py` | `save_record()`, `get_records()`, `update_record()` |
| CSV Export | `pipeline/csv_writer.py` | `append_to_csv()` |
| Pipeline Runner | `pipeline/runner.py` | `process_submission()` |
| Data Models | `pipeline/schema.py` | `SubmissionRecord`, `OcrResult` |

## Acceptance Checklist

Use this checklist to verify Scope 1 functionality:

### Upload Functionality
- [ ] Single file upload works (PNG, JPG, JPEG, PDF)
- [ ] Bulk file upload works (multiple files at once)
- [ ] Upload mode toggle switches between single and bulk modes
- [ ] Files are saved to artifact directories with deterministic IDs
- [ ] Re-uploading the same file generates the same submission_id

### File Type Support
- [ ] PDF files are processed (first page)
- [ ] PNG image files are processed
- [ ] JPG/JPEG image files are processed
- [ ] Scanned documents are processed via OCR
- [ ] Handwritten text is extracted via OCR

### Field Extraction
- [ ] Student name is extracted from forms
- [ ] School name is extracted from forms
- [ ] Grade is extracted and normalized (1-12 or "K")
- [ ] Optional fields (teacher, location, etc.) are extracted when present
- [ ] Missing fields are handled gracefully (set to null)

### Flagging Behavior
- [ ] All records start with `needs_review=True`
- [ ] Missing student name flags as `MISSING_STUDENT_NAME`
- [ ] Missing school name flags as `MISSING_SCHOOL_NAME`
- [ ] Missing grade flags as `MISSING_GRADE`
- [ ] Empty essays flag as `EMPTY_ESSAY`
- [ ] Short essays (< 50 words) flag as `SHORT_ESSAY`
- [ ] Low OCR confidence (< 50%) flags as `LOW_CONFIDENCE`
- [ ] Review reason codes are stored and displayed correctly

### Export Functionality
- [ ] Records are exported to `submissions_clean.csv` when approved
- [ ] Records are exported to `submissions_needs_review.csv` when flagged
- [ ] CSV files have correct headers
- [ ] CSV files use UTF-8 encoding
- [ ] Records are saved to database automatically
- [ ] Manual approval moves records to clean CSV

### Database Storage
- [ ] Records are saved to SQLite database after processing
- [ ] Database records can be queried by `needs_review` status
- [ ] Records can be updated via UI
- [ ] Records can be deleted via UI
- [ ] Database statistics are displayed correctly

### Out-of-Scope Verification
- [ ] No scoring/evaluation functionality exists
- [ ] No reader workflow exists
- [ ] No administrative roles/permissions exist
- [ ] No automatic grade grouping/sorting exists (records ordered by date)
- [ ] All records require manual approval

## Notes

- **Runtime Behavior**: This documentation describes the current runtime behavior without proposing changes
- **Baseline Lock**: Scope 1 represents a locked baseline; future changes will be documented separately
- **Manual Review Required**: All records require manual review and approval before being marked as "clean"
- **Deterministic Processing**: Re-processing the same file will generate the same submission_id and reuse the same artifact directory



