# Regression Harness Debug Note

## Root Causes Found

- Chunk-level reason aggregation inflated batch metrics: `reason_code_counts` was incremented per chunk instead of once per document.
- Missing-field logic was tied to chunk extraction output, not doc-level OCR aggregate text; a field present on any page could still be flagged missing.
- Harness chunk processing forced `stub` OCR provider, causing repeated synthetic OCR text and misleading field-extraction behavior.
- Chunk submission IDs were truncated (`parent_id[:6]`), increasing collision risk across different documents.

## What Changed

- Document-level `final_text` now comes from ordered per-page OCR aggregation and drives grade/school detection.
- `reason_code_counts` are doc-level counts, so each reason is counted at most once per document.
- Template short-circuit now emits `TEMPLATE_ONLY` (and optional `OCR_LOW_CONFIDENCE`) without adding missing-field reasons.
- Missing-field reasons include `missing_field_evidence` payloads with source, patterns, snippet, and submission identifiers.
- OCR per-page guardrails now assert page count and page-index coverage.
- Chunk submission IDs and artifact paths are namespaced by full parent submission ID.

## Quick Verification (Single Document)

1. Run harness on one PDF:
   - `python scripts/regression_check.py --pdf-dir <dir> --pdf-glob 'Valeria-Pantoja.pdf' --ocr-provider <provider> --output-dir artifacts/harness_runs/debug_single`
2. Inspect:
   - `artifacts/harness_runs/debug_single/current/docs/<submission_id>/doc_summary.json`
3. Verify in `doc_summary.json`:
   - `ocr_conf_stats[*].page_index` covers `0..page_count-1`
   - `extracted.grade` and `extracted.school_name` are populated when present in OCR text
   - `reason_codes` excludes `MISSING_GRADE`/`MISSING_SCHOOL_NAME` when extracted fields are found
   - `missing_field_evidence` exists only when a missing-field reason is emitted
