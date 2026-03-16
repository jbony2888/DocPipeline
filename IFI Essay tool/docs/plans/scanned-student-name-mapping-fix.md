# Plan: Fix Scanned Docs Student Name Mapping

## Problem

For **scanned multi-submission** documents (e.g. Andres-Alvarez-Olguin.pdf, Valeria-Pantoja.pdf), the pipeline:
- ✅ Extracts school (Lincoln Middle School) and grade (8)
- ✅ Extracts essay text (154 words)
- ❌ Returns `student_name: null` even though the text contains `"Name: Andrick Vargas Hernandez"`

Heuristics find the name (`Freeform heuristics: student_name='Andrick Vargas Hernandez'`), but the final record has `student_name: null`.

---

## Root Cause

**Location:** `pipeline/runner.py` lines 297–335 (chunk attribution guardrail)

For chunked scanned docs (`is_chunk=True`, `BULK_SCANNED_BATCH`), the runner enforces “metadata must come from the chunk’s start page only”:

1. It runs `_extract_header_fields_from_text(start_page_text)` to get fields from the chunk’s first page.
2. For each field, if `start_fields` has a value → use it; **else → set `contact_fields[key] = None`**.

`_extract_header_fields_from_text` (runner.py:46–71) uses a regex that matches:
- `student's name`, `student name`, `nombre del estudiante`

but **not**:
- `Name:` or `Nombre:`

So `"Name: Andrick Vargas Hernandez"` is not matched, `start_fields["student_name"]` is `None`, and the guardrail overwrites the correct value from `extract_fields_ifi` with `None`.

---

## Implementation Plan

### 1. Extend `_extract_header_fields_from_text` (runner.py)

**Goal:** Match `"Name: X"` and `"Nombre: X"` as student name labels.

**Current pattern:**
```python
"student_name": [
    r"(?im)\b(?:student(?:'s)?\s*name|nombre(?:\s+del)?\s+estudiante)\s*[:\-]?\s*([^\n\r]{2,80})",
],
```

**Change:** Add patterns that match:
- Line-start `Name:` or `Nombre:` (avoid matching `Father-Figure Name`, `Father's Name` by preferring start-of-line or word boundary).

**Proposed patterns:**
```python
"student_name": [
    r"(?im)\b(?:student(?:'s)?\s*name|nombre(?:\s+del)?\s+estudiante)\s*[:\-]?\s*([^\n\r]{2,80})",
    r"(?im)^\s*name\s*[:\-]\s*([^\n\r]{2,80})",           # "Name: Andrick Vargas Hernandez"
    r"(?im)^\s*nombre\s*[:\-]\s*([^\n\r]{2,80})",         # "Nombre: ..."
],
```

Add logic so we do not treat `"Father-Figure Name:"` or `"Father's Name:"` as the student name (e.g. skip lines containing `father`).

---

### 2. Avoid overwriting with `None` when attribution is ambiguous

**Location:** runner.py lines 328–335

**Current behavior:** If `start_fields[key]` is empty, always set `contact_fields[key] = None`.

**Proposed behavior:** Only overwrite when we are enforcing attribution and the field was found on a non-start page. If `start_fields` is empty and the chunk’s first page has limited or stub OCR, preserve the value from `extract_fields_ifi` instead of clearing it.

**Change:**
```python
# Instead of: contact_fields[key] = None when start_fields is empty
# Only clear when we have evidence the field came from a non-start page
if not multi_page_typed:
    if found_on_non_start[key]:
        contact_fields[key] = None  # Field was on wrong page, clear it
    # else: keep contact_fields[key] from extract_fields_ifi (don't overwrite with None)
```

This keeps behavior when attribution is risky but avoids wiping good data when `start_fields` is empty (e.g. stub OCR or odd formatting).

---

### 3. Optional: Broaden `_extract_unlabeled_header_metadata` (extract_ifi.py)

**Current behavior:** Skips lines containing `"name"` or `"nombre"` when looking for a plausible student name (to avoid labels).

**Issue:** Lines like `"Name: Andrick Vargas Hernandez"` are skipped.

**Proposed change:** Add a special case for `"Name: X"` / `"Nombre: X"` and treat the part after the colon as the student name when it passes `is_plausible_student_name`.

---

## Implementation Order

1. **Step 1:** Extend `_extract_header_fields_from_text` in `runner.py` (highest impact, small change).
2. **Step 2:** Adjust guardrail overwrite logic in `runner.py` so we don’t clear fields when `start_fields` is empty and there’s no attribution risk.
3. **Step 3:** If needed, extend `_extract_unlabeled_header_metadata` for `"Name:"` / `"Nombre:"` patterns.

---

## Verification

After changes:

1. Run verification script with `--ocr-provider stub`:
   ```bash
   python scripts/run_feedback_verification.py --input-dirs docs/client_test_instructions/scanned_multi_submission --output verification_scanned.json
   ```
2. Confirm `student_name` is populated (e.g. `"Andrick Vargas Hernandez"`) in the scanned records.
3. Test in the app with Google Vision OCR on the same scanned PDFs.

---

## Files to Modify

| File | Changes |
|------|---------|
| `pipeline/runner.py` | 1) Add `Name:` / `Nombre:` patterns to `_extract_header_fields_from_text`; 2) Adjust chunk guardrail overwrite logic |
| `pipeline/extract_ifi.py` | (Optional) Add `Name:` / `Nombre:` handling in `_extract_unlabeled_header_metadata` |
