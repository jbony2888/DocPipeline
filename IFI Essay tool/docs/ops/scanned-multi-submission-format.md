# Scanned multi-submission format (IFI essay forms)

## Doc type

**Scanned multi-submission** = a single PDF containing **multiple essay submissions** where each submission is a **scanned image** of the IFI essay form (same form as typed, but photographed/scanned). Essays are typically **handwritten**, requiring OCR for text extraction.

- **Format**: `image_only` (no PDF text layer)
- **Structure**: `multi` (multiple records from one file)
- **Form layout**: `ifi_official_scanned` when IFI form labels are detected in OCR output

## Detection (is it detectable?)

Yes. The pipeline detects this as a **scanned image of the form** and classifies it so that **OCR and Groq** are used:

- **doc_class**: `BULK_SCANNED_BATCH` (multiple submissions in one scanned file)
- **format**: `image_only` (no PDF text layer → OCR is used per chunk)
- **is_scanned_multi_submission**: `True` when format=image_only, structure=multi, chunks > 1

Detection steps:

1. **Format**: All pages have `text_layer_chars == 0` → `image_only`
2. **Structure**: Multiple pages with IFI header-like content (Student's Name, Grade, School, etc.) in the top 25% strip → `multi`
3. **Form layout**: Aggregated OCR top-strip text matches relaxed IFI labels → `ifi_official_scanned`
4. **Flag**: `is_scanned_multi_submission = True` when format=image_only, structure=multi, chunks > 1

## Dark band (black space) detection

Thick dark horizontal bars between submissions are detected via pixel analysis:

- **`detect_dark_horizontal_bands()`**: Renders each page to grayscale and finds contiguous dark rows (luminance below threshold). Returns `(y_start_ratio, y_end_ratio)` for each band.
- **`_has_dark_band_near_top()`**: True when a band intersects the top ~15% of the page — indicates content below is a new submission.
- **Refinement**: When every page is initially marked as a submission start (over-chunking), pages with a dark band at top are preferred as boundaries; pages without are treated as continuations.

Dark bands are stored in `PageAnalysis.dark_bands` for each scanned page.

## Relaxed detection for handwritten OCR

Handwritten text and scanned forms often produce OCR output with:

- Character substitutions (l→1, 0→O)
- Missing or extra characters (studnt, garde, schol)
- Variable spacing

The pipeline uses:

- **Relaxed header keywords**: `studnt`, `garde`, `schol`, `escue`, etc. in addition to standard labels
- **Lower thresholds** for image_only/hybrid: header score ≥ 0.15, chars ≥ 5 (vs 0.2 / 10 for typed)
- **Lower OCR confidence blocking**: 0.35 (vs 0.45) so handwritten OCR (typically 0.4–0.6) is not over-blocked
- **Periodic heuristic**: For 6+ pages with only one detected start, check every 2nd page for header-like content (IFI forms are ~2–3 pages each)

## Processing strategy (OCR + Groq)

Because the doc is detected as scanned (image_only) and not a typed form:

1. **OCR**: Each chunk (page) has no text layer, so the runner uses the OCR provider (Google Cloud Vision by default) to extract text from the scanned images. Handwriting is supported. Set `ocr_provider=google` in jobs.
2. **Bulk batch (doc_class = BULK_SCANNED_BATCH)**: One submission per page (no chunk-level extraction). Each page is extracted independently; parent file is a container only (not saved as a submission). Ensures no cross-contamination of fields across pages; review state is computed per new submission. Idempotent via deterministic submission IDs per page.
3. **Other multi-page**: Split by `chunk_ranges` from document analysis; each chunk becomes one submission record.
4. **Normalization**: Groq LLM normalizes the OCR text to schema fields (student_name, school_name, grade, etc.). Used in `extract_ifi.extract_ifi_submission()` for non–typed-form docs; system prompt: "You normalize OCR text from scanned documents into structured fields...". OpenAI is not used.
5. **Fallback**: When GROQ_API_KEY is unset, rule-based extraction is used instead.

## Test set

- **Location**: `docs/multi-submission-docs /` (scanned image PDFs with multiple essays; folder name has a trailing space)
- **Run with Google OCR** (requires `GOOGLE_APPLICATION_CREDENTIALS` and network). Run from the **main repo** (not a worktree); the script lives under `IFI Essay tool/`:
  ```bash
  cd "/path/to/DocPipeline/IFI Essay tool"
  python scripts/regression_check.py --pdf-dir "docs/multi-submission-docs " --ocr-provider google --output-dir artifacts/harness_runs/scanned_multi_test
  ```
- **Run with stub OCR** (offline; validates BULK_SCANNED_BATCH detection and page-level splitting; extraction uses placeholder text):
  ```bash
  python scripts/regression_check.py --pdf-dir "docs/multi-submission-docs " --ocr-provider stub --output-dir artifacts/harness_runs/scanned_multi_test_stub
  ```

## Implementation notes

- **document_analysis**: `detect_ifi_official_scanned_form()` for form layout; relaxed header scoring; periodic multi heuristic
- **ocr.py**: `ocr_pdf_pages()` with mode=full for all pages; top_strip used during analysis
- **runner**: Uses OCR path (no text layer) for image_only chunks; `process_submission` per chunk
- **jobs/process_submission**: For BULK_SCANNED_BATCH uses `get_page_level_ranges_for_batch(page_count)` (one submission per page); otherwise iterates over `analysis.chunk_ranges`. Each unit OCR'd and extracted separately. Child records store doc_class=SINGLE_SCANNED.
