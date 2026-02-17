# Typed freeform essays (standard freeform)

**Typed submissions**: PDFs with extractable text (no OCR). The pipeline uses the **PDF text layer** and **Groq** to normalize name/school/grade.

- **Format**: `native_text` (from document_analysis when pages have a text layer).
- **Extraction**: Text from PyMuPDF; no Google Vision. Groq normalizes header metadata (student_name, school_name, grade). Without `GROQ_API_KEY`, rule-based heuristics are used.

## Run tests

From the **main repo** (e.g. `DocPipeline/IFI Essay tool`):

```bash
cd "/path/to/DocPipeline/IFI Essay tool"
set -a && source .env && set +a   # load GROQ_API_KEY for Groq normalization
python -m pytest tests/test_standard_freeform_essay.py -v
```

## Run regression harness

```bash
cd "/path/to/DocPipeline/IFI Essay tool"
set -a && source .env && set +a
python scripts/regression_check.py --pdf-dir "docs/standard_freeform_essay" --ocr-provider stub --output-dir artifacts/harness_runs/typed_freeform_test
```

Use `--max-docs N` to limit how many PDFs are processed. For typed PDFs, `--ocr-provider stub` is fine; text comes from the PDF layer, not OCR.
