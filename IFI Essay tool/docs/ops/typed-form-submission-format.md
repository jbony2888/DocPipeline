# Typed form submission format (IFI official essay form)

## Doc type

**Typed form submission** = official IFI essay form where content is **native PDF text** (typed, not scanned). No OCR is required; text can be extracted directly from the PDF text layer (and, when present, from AcroForm field values).

**Canonical form (used for this doc type from now on):** **26-IFI-Essay-Form-Eng-and-Spanish** (e.g. `26-IFI-Essay-Form-Eng-and-Spanish.pdf`, filled: `26-IFI-Essay-Form-Eng-and-Spanish-filled.pdf`). Legacy 22-IFI forms (e.g. `22-IFI-Essay-Form-34.pdf`, Kami exports) are still supported.

**Bilingual (English + Spanish):** Metadata labels are accounted for in both languages. Detection and extraction use Spanish aliases (e.g. Nombre del Estudiante, Grado, Escuela, Nombre del Padre/Figura Paterna, Teléfono, correo) in `document_analysis` and `extract.py`.

## Format detection

- **Format**: `native_text` (from `document_analysis` when every page has `text_layer_chars > 0`).
- **Structure**: Usually `single` (one submission) or `template` (blank/minimally filled). Filled typed forms should be treated as `single` with metadata present.
- **Form layout** (`form_layout: "ifi_official_typed"`): Detected by consistent labels in fixed positions:
  - **Top zone**: "IFI Fatherhood Essay Contest", "Student's Name", optionally "Grade/Grado", "School/Escuela"
  - **Bottom zone**: "Email", "Phone", "Father/Father-Figure Name"
  - Detection uses `detect_ifi_official_typed_form()` in `document_analysis.py` (normalizes Unicode apostrophes for matching).

## Canonical form: 26-IFI-Essay-Form-Eng-and-Spanish

- **Contest:** 2026 IFI Fatherhood Essay Contest.
- **AcroForm fields (when filled):** Student's Name, Grade, School, Essay, Dad's Name, Dad's Email, Dad's Phone, Dad's Response, Group1 (Writing About: Father/Grandfather/Stepdad/Father-Figure).
- **Form field values** are merged into the extracted text in `extract_pdf_text_layer()` so the same rule-based extraction works for both text-layer-only PDFs and filled AcroForm PDFs.

## Typical layout (22-IFI legacy and 26-IFI)

Text order from the PDF text layer (and merged form fields when present); reading order may vary by PDF:

- **Metadata fields (value on same line as label)**: Student's Name, Father/Father-Figure Name, Phone, and Email — the value appears **right next to** the label on the **same line**, not on the next line.
- **Block labels (content on next line(s))**: "Father/Father-Figure reaction to this essay" and "What my Father or an Important Father Figure Means to Me" — the **label** is on one line; the essay body or parent reaction text is on the **next line(s)**.

1. **Header**
   - "2022 IFI Fatherhood Essay Contest"
   - **Student's Name** (label) → value on **same line** (e.g. "Student's Name Jordan Altman")
   - Essay title/prompt: "What My Father or an Important Father-Figure* Means to Me" (essay text follows on next line(s))
   - **Grade / Grado**, **School / Escuela** (label) → value on same line
2. **Essay body**
   - Filled essay text
3. **Footer / parent section**
   - "Father/Father-Figure reaction to this essay:" → parent text on **next line(s)**
   - **Father/Father-Figure Name**, **Email**, **Phone** → value on **same line** as each label
   - Footnote: "*A Father-Figure can be..."

## Metadata to extract

| Field           | Source in form                    | Flag if missing? |
|----------------|------------------------------------|------------------|
| student_name   | Near "Student's Name" / "Nombre del Estudiante" | Yes |
| grade          | Near "Grade" / "Grado"            | Yes (1–12 or K) |
| school_name    | Near "School" / "Escuela"        | Yes |
| email          | Near "Email" (bottom zone)       | No – extract when available |
| phone          | Near "Phone" (bottom zone)       | No – extract when available |
| father_figure_name | Near "Father/Father-Figure Name" | No |
| essay_text     | Between prompt and parent reaction | Yes (EMPTY_ESSAY) |

## Processing strategy

1. **No OCR**: Use PyMuPDF `page.get_text("text")` for native_text PDFs. Do not call Google Vision.
2. **No LLM**: Use rule-based extraction only (layout + label proximity). Skip `extract_ifi_submission` when typed form is detected.
3. **Segmentation**: `split_contact_vs_essay` on extracted text.
4. **Extraction**: `_extract_ifi_typed_form_by_position` – same-line only for Student's Name, Father/Father-Figure Name, Phone, Email (value right next to label); fallback for student name from first line after footnote when same-line not found.
5. **Validation**: Same as other submissions (MISSING_GRADE, MISSING_SCHOOL_NAME, etc.).

## Test set and run

- **Location**: `docs/typed-form-submission/`
- **Run**:
  ```bash
  python scripts/regression_check.py --pdf-dir docs/typed-form-submission --ocr-provider google --output-dir artifacts/harness_runs/typed_forms_test
  ```

## Expected extraction (typed-form-submission)

| Doc | student_name | Notes |
|-----|--------------|-------|
| **26-IFI-Essay-Form-Eng-and-Spanish-filled.pdf** | Test Student Garcia | ✓ Canonical form, filled; form fields merged into text |
| 22-IFI-Essay-Form-34.pdf | Jordan Altman | ✓ Legacy |
| 22-IFI-Essay-Form-35.pdf | christian santacruz | ✓ Legacy |
| Kami-Export-22-IFI-Essay-Form-1-2.pdf | Giovanni Ruiz | ✓ Legacy |
| Kami-Export-22-IFI-Essay-Form-2-2.pdf | Francely Pacheco | ✓ Legacy (full-scan fallback) |
| Maritza-Medrano-... | null | Essay starts immediately (no name in text) |

## Implementation notes

- **document_analysis**: Sets `format = "native_text"` when all pages have a text layer; `detect_ifi_official_typed_form()` matches 22-IFI and 26-IFI layouts by labels.
- **ocr.py**: For typed forms, `extract_pdf_text_layer()` merges AcroForm field values (Student's Name, Grade, School, Dad's Name, Dad's Email, Dad's Phone, etc.) into the page-0 text so rule-based extraction sees them.
- **Runner**: When input is a PDF and all pages have text layer, build `OcrResult` from text layer (and form fields) and skip `process_image()`.
- **Regression harness**: For `analysis.format == "native_text"`, uses text-layer extraction (and form-field merge) instead of `ocr_pdf_pages()`, avoiding OCR for typed forms.
