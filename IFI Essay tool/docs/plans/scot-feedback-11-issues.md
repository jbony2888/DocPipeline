# Scot's Feedback: 11 Processing Issues – Status & Plan

This document maps each feedback item to the pipeline, tracks remediation status, and notes next steps.

---

## Issue 1: Multiple-entries file – "Empty Essay" and "Template Only" (essay visible in side-by-side)

**Description:** A multi-entry file processed, but each record shows "Empty Essay" and "Template Only (no submission)" even though the essay content is visible in the side-by-side view. Correctly shows no school/grade.

**Root cause (likely):** Essay segmentation failing for this layout—essay text exists but isn't extracted into `essay_text`, so `word_count=0` and validation flags `EMPTY_ESSAY` + `TEMPLATE_ONLY`.

**Status:** 🔴 **Needs investigation**

**Pipeline areas:**
- `pipeline/extract_ifi.py` – essay segmentation, contact_block vs essay_block split
- `pipeline/validate.py` – EMPTY_ESSAY, TEMPLATE_ONLY codes
- Side-by-side may show raw OCR/text while extraction produces empty essay block

**Next steps:** Identify the specific test file; run with `--ocr-provider google` and inspect `artifacts/<submission_id>/` (contact_block.txt, essay_block.txt, raw_text.txt) to see where essay content is lost.

---

## Issue 2: Tonni Lumu, Kamila Blades – only first page processed (metadata page; essay on page 2)

**Description:** Two-page submissions: page 1 = metadata form, page 2 = essay. Pipeline only processes page 1, missing the essay.

**Root cause:** When page 2 had no text layer (image/scanned essay), `get_ocr_result_from_pdf_text_layer` only returned page 0 text, so essay on page 2 was never included.

**Status:** 🟢 **Fixed**

**Fix (in `pipeline/ocr.py`):** In `get_ocr_result_from_pdf_text_layer`, when the PDF has 2+ pages and any page after the first has no text, return `None` so the runner uses OCR (e.g. Google Vision renders and OCRs all pages). That way page 2 content is included.

---

## Issue 3: Stella Doran – metadata in file but AI didn't pick it up

**Description:** Metadata present in the document; extraction failed to capture it.

**Status:** 🟡 **Partially addressed** (Groq + unlabeled patterns improved many cases)

**Pipeline areas:**
- `pipeline/extract_ifi.py` – LLM extraction, unlabeled header metadata
- Groq normalization for typed freeform

**Next steps:** Test Stella Doran file with Groq enabled; check if format (typed vs scanned) affects extraction. Add to verification suite if reproducible.

---

## Issue 4: Henry Yedinak, Bevin Brummel – name only, unlabeled; AI didn't pick it up

**Description:** Name appears in the file without a label. Scot suspects AI can't identify unlabeled names on its own.

**Status:** 🟠 **Known limitation**

**Pipeline areas:**
- `pipeline/extract_ifi.py` – `_extract_unlabeled_header_metadata` heuristics
- Groq prompt for freeform documents

**Next steps:** Consider extending unlabeled-name heuristics (e.g., "first line that looks like a name" when no labels exist). Low confidence—may require filename fallback (e.g., Henry-Yedinak-Essay.pdf → candidate name).

---

## Issue 5: Angel Sagado – PNG didn't process but said it did (tried twice)

**Description:** PNG file; processing reports success but no record. Silent failure or misleading status.

**Status:** 🟢 **Fixed**

**Fix:** In `jobs/process_submission.py`, PNG/JPEG images are now converted to a single-page PDF at the start of the job (same as Word→PDF). The pipeline then always receives a PDF, so `analyze_document` and `fitz.open(processing_path)` no longer depend on PyMuPDF’s image-opening behavior. Conversion uses `_image_to_pdf()` (PyMuPDF: open image or insert_image onto a new page, save to temp PDF). If conversion fails, the job raises a clear `ValueError` instead of failing later with a cryptic error. This makes PNG submissions (e.g. Angel Sagado) process reliably and fail visibly when the file is bad.

---

## Issue 6: Nya Aldridge – standard format, labeled "Student's Name", but not picked up

**Description:** Standard template with labeled Student's Name; extraction missed it.

**Status:** 🟢 **Fixed**

**Fix:** (1) **Unicode apostrophe**: Many PDFs/Word use Unicode RIGHT SINGLE QUOTATION MARK (U+2019) instead of ASCII apostrophe, so "Student's Name" in the doc didn't match our aliases. `extract.py` already normalizes these in `normalize_text()`; (2) **runner.py** `_extract_header_fields_from_text`: student_name regex now allows either apostrophe via `(?:[\u2019']s)?` and added a pattern that captures the value when it appears on the **next line** (label on one line, name on the next), so standard forms with that layout are picked up.

---

## Issue 7: Godinez essay – Word (.DOC) not showing as upload option

**Description:** .DOC file not available to upload. Scot wants .DOC support alongside PDF, PNG, JPG.

**Status:** 🟢 **Fixed**

**Current implementation:**
- `flask_app.py`: `ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf", "doc", "docx"}`
- `templates/dashboard.html`: `accept=".png,.jpg,.jpeg,.pdf,.doc,.docx"`
- `pipeline/word_converter.py`: Converts .doc via LibreOffice, .docx via python-docx

**Fix:** Backend already allowed `.doc`/`.docx` case-insensitively. Updated `templates/dashboard.html`: (1) added MIME types to the file input `accept` attribute (`application/msword`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`) so file pickers show Word documents reliably; (2) clarified helper text to "Word (.doc, .docx)"; (3) added Word icon (`bi-file-earmark-word`) for .doc/.docx in the selected-files list.

---

## Issue 8: Fatherhood Essay, Janette Zetina Alvise – unlabeled name/school not picked up

**Description:** Student Name and School Name in file but unlabeled; not extracted.

**Status:** 🟢 **Fixed** (Groq + unlabeled extraction)

**Verification:** Mayra-Martinez and Janette Zetina now extract correctly with Groq. Fatherhood Essay (Cesar Zaragoza style) and Janette-Zetina-Aviles-Farherhood-Essay.pdf verified in standard_freeform_essay run.

---

## Issue 9: Kami, Maritza Medrano – standard template, no metadata or essay pulled

**Description:** Standard IFI form; metadata (and sometimes essay) not extracted. Maritza’s PDF has the Essay form field filled but Student’s Name form field empty; name appears only in the filename.

**Status:** 🟢 **Fixed (student name)**

**Fix:** In `pipeline/runner.py`, added `_student_name_from_filename(original_filename)` and a fallback: when `student_name` is still None after form/extraction, parse the filename for a plausible "First-Last" name (e.g. `Maritza-Medrano-2022-IFI-Fatherhood-Essay-Contest.pdf` → "Maritza Medrano") and set it if it passes `is_plausible_student_name`. Essay was already being extracted from the Essay form field (word_count 1180). School/grade remain null for the 22-IFI form variant that doesn’t include those fields.

---

## Issue 10: Mayra-Martinez – unlabeled name/school + only first page (missing page 2 essay)

**Description:** Same as #8 (unlabeled) plus only first page processed; second page essay missing.

**Status:** 🟢 **Fixed**

- **Name/school:** Fixed with Groq normalization (Mayra Martinez, Rachel Carson Elementary).
- **Second page essay:** Fixed with #2—when any non-first page has no text layer, pipeline now falls back to OCR so all pages are included (see `pipeline/ocr.py` `get_ocr_result_from_pdf_text_layer`).

---

## Issue 11: Valerie Pantoja – 8 submissions × 2 pages each; processed as 16 (two per submission)

**Description:** 8 submissions, each with metadata on page 1 and essay on page 2. Pipeline treats each page as a separate submission (16 records instead of 8).

**Root cause:** `get_batch_iter_ranges` uses `_is_metadata_essay_alternating_pattern` to pair pages. If detection fails, it falls back to `get_page_level_ranges_for_batch` → one record per page.

**Status:** 🟡 **Logic exists, detection may be failing**

**Pipeline areas:**
- `pipeline/document_analysis.py` – `_is_metadata_essay_alternating_pattern`, `get_paired_metadata_essay_ranges`
- Detection requires: even pages have IFI header, odd pages have low header score; `page_count % 2 == 0`

**Next steps:** Run Valeria-Pantoja.pdf with verbose logging; check if alternating pattern is detected. If not, relax detection thresholds or add explicit "2 pages per submission" heuristic for this layout. Valeria Pantoja is in `docs/client_test_instructions/scanned_multi_submission/`.

---

## Summary: What's Fixed vs Remaining

| # | Issue | Status |
|---|-------|--------|
| 1 | Multiple entries – Empty Essay / Template Only | 🔴 Investigate |
| 2 | Tonni Lumu, Kamila Blades – only page 1 | 🟢 Fixed |
| 3 | Stella Doran – metadata not picked up | 🟡 Test with Groq |
| 4 | Henry Yedinak, Bevin Brummel – unlabeled name only | 🟠 Known limitation |
| 5 | Angel Sagado – PNG said processed, didn't | 🟢 Fixed |
| 6 | Nya Aldridge – labeled name not picked up | 🟢 Fixed |
| 7 | Godinez .DOC not uploadable | 🟢 Fixed |
| 8 | Fatherhood, Janette Zetina – unlabeled name/school | 🟢 Fixed |
| 9 | Maritza Medrano – no metadata or essay | 🟢 Fixed (name from filename) |
| 10 | Mayra-Martinez – unlabeled + missing page 2 | 🟢 Fixed |
| 11 | Valerie Pantoja – 16 instead of 8 submissions | 🟡 Pairing logic exists; verify detection |

---

## Recommended Priority Order

1. **#11 Valerie Pantoja** – High impact; metadata+essay pairing already implemented; verify/fix detection.
2. **#2 & #10** – Multi-page single: ensure page 2 (essay) is included in extraction.
3. **#1 Multiple entries** – Empty Essay / Template Only; debug segmentation for batch layout.
4. **#5 Angel Sagado PNG** – Silent failure; fix status reporting and PNG path.
5. **#9 Maritza Medrano** – Full extraction failure; root cause unknown.
6. **#6 Nya Aldridge** – Labeled name; likely pattern or OCR variant.
7. **#7 Godinez .DOC** – Fixed (accept + MIME types, helper text, Word icon).
8. **#3 Stella Doran** – Test with Groq.
9. **#4 Henry/Bevin** – Consider unlabeled-name heuristics or filename fallback.
