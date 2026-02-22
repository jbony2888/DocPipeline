# Client Test Instructions: Standard Freeform Essay (Typed PDFs)

This document explains how to test **standard freeform essays**—typed PDFs with a text layer (no scanning, no OCR).

## What You're Testing

- **Format**: Typed PDFs that contain extractable text. The pipeline uses the **PDF text layer** and **Groq** to normalize student name, school, grade, and essay content.
- **No OCR**: Because these are typed, OCR is not needed. `--ocr-provider stub` is sufficient for regression runs.
- **Groq**: For best results, set `GROQ_API_KEY` in your environment. Without it, rule-based heuristics are used.

## Test Files

The test PDFs are in **this folder**:

- Father-Hood-Essay-1.pdf
- Fatherhood-Essay-1-5.pdf
- Fatherhood-Essay-14.pdf
- Fatherhood-Essay-Ashley.pdf
- Fatherhood-Essay-Jose-.pdf
- Fatherhood-Essay_-Cesar-Zaragoza.pdf
- Fatherhood-essay-.pdf
- Fatherhood-essay-Diego.pdf
- Fatherood-Essay.pdf
- Janette-Zetina-Aviles-Farherhood-Essay.pdf
- Mayra-Martinez-Fatherhood-Essay.pdf
- fatherhood-Essay-2022.pdf

## How to Test via the Web App

1. Go to the **IFI Essay Gateway** dashboard.
2. Open **1️⃣ Upload Entry Forms**.
3. Choose **Multiple Entries** (or Single Entry).
4. Select one or more PDFs from this folder.
5. Click **Process Entries**.
6. Wait for the email notification.
7. Open **Needs Review** or **All Records**.
8. **Verify**: Each record should show extracted student name, school, grade, and essay text from the typed content. No OCR should be involved.

## Running the Regression Harness (Optional)

Load your environment (including `GROQ_API_KEY` if available) and run:

```bash
cd "IFI Essay tool"
set -a && source .env && set +a
python scripts/regression_check.py \
  --pdf-dir "docs/client_test_instructions/standard_freeform_essay" \
  --ocr-provider stub \
  --output-dir artifacts/harness_runs/typed_freeform_test
```

Use `--max-docs N` to limit how many PDFs are processed (e.g., `--max-docs 3` for a quick smoke test).
