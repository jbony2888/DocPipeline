# Review reason codes — what they mean & how to clear them

Stored in DB as `review_reason_codes`: **semicolon-separated** enums (e.g. `MISSING_STUDENT_NAME;SHORT_ESSAY`).  
Canonical list: **`ALLOWED_REASON_CODES`** in `idp_guardrails_core/core.py` (also used by `pipeline/validate.py`).

---

## Required fields (IFI policies)

For IFI doc types, **`validate.py`** requires **student_name**, **school_name**, and **grade** (plus essay rules below). “Missing” uses stricter checks than “empty string” — e.g. labels like `Student's Name` or `Escuela` alone count as **missing**.

| Code | Meaning | Why it appears | Fix (operator) | Fix (pipeline / dev) |
|------|---------|----------------|----------------|----------------------|
| **MISSING_STUDENT_NAME** | No usable student name | Blank, label text, or value rejected as too long / sentence-like (essay leaked into name) | Open record → type correct name → save; or approve if name is elsewhere on PDF | Improve OCR; tune `extract_ifi` / form fields; filename fallback in `runner` only helps some cases |
| **MISSING_SCHOOL_NAME** | No usable school | Blank, `Escuela`/`School` only, or essay-like blob in school field | Enter school in app | Same + field attribution guardrails (`POSSIBLE_FIELD_SWAP`) |
| **MISSING_GRADE** | Grade empty or unreadable | Not extracted, illegible | Enter grade | `normalize_grade` / IFI form grade box extraction |
| **INVALID_GRADE_RANGE** | Grade present but not normalized to allowed set | Weird text that isn’t K–12 / Pre-K etc. | Correct grade in UI | Expand `normalize_grade` if legit local labels missing |

---

## Essay content

| Code | Meaning | Why | Operator fix | Dev fix |
|------|---------|-----|--------------|---------|
| **EMPTY_ESSAY** | `word_count == 0` | OCR got no essay body, wrong segmentation, or scanned blank | Re-upload clearer scan; use Review to check PDF | Segmentation (`segment.py`), OCR quality, IFI essay region detection |
| **SHORT_ESSAY** | `0 < word_count < 50` (policy `min_essay_words`) | Very little text in essay zone | Confirm real essay is short vs extraction miss | Lower threshold only if business allows (policy in `idp_guardrails_core` `ValidationPolicy`) |

---

## Document type & template

| Code | Meaning | Why | Operator fix | Dev fix |
|------|---------|-----|--------------|---------|
| **TEMPLATE_ONLY** | Classified as empty template (`doc_type == template`) | No real handwriting/fill detected | User should submit filled form | `document_analysis` / template detection tuning |
| **DOC_TYPE_UNKNOWN** | Couldn’t classify document type | Unusual layout or corrupt PDF | Manual review; re-upload | Classification heuristics in `document_analysis.py` |

---

## OCR & extraction quality

| Code | Meaning | Why | Operator fix | Dev fix |
|------|---------|-----|--------------|---------|
| **OCR_LOW_CONFIDENCE** | Scanned doc + confidence below policy floor (e.g. min 0.50 for scanned IFI) | Bad scan, faint pencil, skew | Better scan / resubmit | `min_ocr_confidence` per policy in core; OCR provider/settings |
| **EXTRACTION_FALLBACK_USED** | Pipeline used fallback extractor (not primary IFI path) | Primary extraction failed partially | Review fields carefully | Stabilize primary path in `extract_ifi` / runner |

---

## School list & field mix-ups

| Code | Meaning | Why | Operator fix | Dev fix |
|------|---------|-----|--------------|---------|
| **UNKNOWN_SCHOOL** | School string didn’t match reference list | Typo, informal name, or wrong text in school field | Fix spelling or pick from district list | Update `SchoolReferenceValidator` reference data |
| **POSSIBLE_FIELD_SWAP** | Heuristic: student vs school may be swapped | Similar strings or attribution error | Swap/correct in Review UI | `is_name_school_possible_swap` in guardrails core |

---

## “Why in review” shows **—** (empty)

- **`needs_review = true`** but **`review_reason_codes`** empty → often **legacy row** or edge path; opening **Review** in the main app may **backfill** codes (see `flask_app.py` review route).
- If codes exist but UI shows **—**: code might be **legacy / not in `ALLOWED_REASON_CODES`** anymore — those are **filtered out** in `format_review_reasons` and display as blank for unknown tokens.

---

## Codes in UI maps but not in `ALLOWED_REASON_CODES`

**`FIELD_ATTRIBUTION_RISK`** / **`LOW_CONFIDENCE`** appear in `format_review_reasons` for display only. **New** validation only emits **`OCR_LOW_CONFIDENCE`**. Old DB rows might still say `LOW_CONFIDENCE`; they won’t validate as “allowed” in strict filters but may still show in exports.

---

## Quick “what do I do?”

1. **Missing name/school/grade** → **Edit record** in the app (or bulk edit) with correct metadata.  
2. **Empty / short essay** → Check **download original**; if essay is there, it’s **extraction** — dev path; if not, user submitted blank/poor scan.  
3. **Template only** → Expect a **resubmission**.  
4. **OCR low confidence** → **Rescan** or accept manual entry after reading PDF.  
5. **Unknown school** → **Correct spelling** or adjust reference list for your program.

---

## Where logic lives (for you + dev)

| Piece | File |
|--------|------|
| Allowed codes | `idp_guardrails_core/core.py` → `ALLOWED_REASON_CODES` |
| Policies (min words, OCR floor, required fields) | Same file → `ValidationPolicy` / `get_policy` |
| Applying codes | `pipeline/validate.py` → `validate_submission_record` (approx. lines 306–394) |
| Human labels in Flask | `flask_app.py` → `format_review_reasons` |
| Human labels in Admin | `admin/routes.py` → `_REVIEW_REASON_MAP` (subset; add any missing codes to match Flask) |

To **add** a new code: extend **`ALLOWED_REASON_CODES`**, then **`validate.py`** (or guardrails), then **admin + Flask** label maps.
