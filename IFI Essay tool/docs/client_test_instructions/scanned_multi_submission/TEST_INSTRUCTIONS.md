# Client Test Instructions: Scanned Multi-Submission (One File, Multiple Essays)

This document explains how to test **scanned multi-submission** PDFs—single files containing **multiple scanned essay images** (handwritten or typed scans).

## What You're Testing

- **Format**: One PDF with multiple pages; each page (or submission chunk) is a **scanned image** of an IFI essay form.
- **Detection**: The pipeline detects this as `BULK_SCANNED_BATCH` and creates **one record per submission** (typically one per page).
- **OCR**: Text is extracted via OCR (Google Cloud Vision by default). No PDF text layer is used.

## Test Files

The 3 test PDFs are in **this folder**:

- Andres-Alvarez-Olguin.pdf
- Andrick-Vargas-Hernandez.pdf
- Valeria-Pantoja.pdf

## How to Test via the Web App

1. Go to the **IFI Essay Gateway** dashboard.
2. Open **1️⃣ Upload Entry Forms**.
3. Choose **Single Entry** or **Multiple Entries** as needed.
4. Upload **one** of the multi-submission PDFs (e.g., `Andres-Alvarez-Olguin.pdf`).
5. Click **Process Entries**.
6. Wait for the email notification.
7. Open **Needs Review** or **All Records**.
8. **Verify**: You should see **multiple records** from the single file—one per scanned submission/page. Each record should have extracted (or OCR'd) fields: student name, school, grade, and essay text.

## Important: OCR Configuration

For **real extraction** from scanned images, the app must use **Google Cloud Vision** for OCR. This requires:

- `GOOGLE_APPLICATION_CREDENTIALS` set in the environment
- Network access to Google Cloud

If OCR is not configured, the pipeline will still run but extraction may use placeholders. Check your deployment settings.

## Running the Regression Harness (Optional)

**With Google OCR** (requires credentials and network):

```bash
cd "IFI Essay tool"
python scripts/regression_check.py \
  --pdf-dir "docs/client_test_instructions/scanned_multi_submission" \
  --ocr-provider google \
  --output-dir artifacts/harness_runs/scanned_multi_test
```

**With stub OCR** (offline; validates batch detection and page splitting; extraction uses placeholder text):

```bash
cd "IFI Essay tool"
python scripts/regression_check.py \
  --pdf-dir "docs/client_test_instructions/scanned_multi_submission" \
  --ocr-provider stub \
  --output-dir artifacts/harness_runs/scanned_multi_test_stub
```
