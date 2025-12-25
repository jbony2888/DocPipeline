# EssayFlow - Handwritten Essay Processor

A modular Python + Streamlit prototype for processing single-page handwritten essay contest submissions.

## Overview

EssayFlow extracts contact information, separates essay content, computes metrics, and validates submissions through a staged pipeline. Each submission is processed through:

1. **Ingestion** - Upload handling and artifact directory creation
2. **OCR** - Text extraction from handwritten images
3. **Segmentation** - Separation of contact info from essay body
4. **Extraction** - Structured field parsing and metric computation
5. **Validation** - Required field checking and quality flags
6. **Export** - CSV output for clean and needs-review records

## Features

- ✅ Modular pipeline architecture
- ✅ Pydantic-based validation
- ✅ Artifact generation at each stage
- ✅ Handles inconsistent handwriting
- ✅ Optional field support (teacher, location)
- ✅ Automatic CSV routing (clean vs. needs review)
- ✅ Stub OCR provider (real OCR integration ready)

## Project Structure

```
essayflow/
├── app.py                  # Streamlit UI
├── requirements.txt        # Python dependencies
├── .gitignore             # Git ignore rules
├── pipeline/              # Core pipeline modules
│   ├── __init__.py
│   ├── schema.py          # Pydantic data models
│   ├── ingest.py          # File upload handling
│   ├── ocr.py             # OCR provider abstraction
│   ├── segment.py         # Contact/essay segmentation
│   ├── extract.py         # Field extraction & metrics
│   ├── validate.py        # Validation logic
│   ├── csv_writer.py      # CSV export
│   └── runner.py          # Pipeline orchestration
├── artifacts/             # Generated at runtime
└── outputs/               # CSV output files
```

## Setup

### 1. Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run Application

```bash
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`

## Usage

### Processing a Submission

1. **Upload** a handwritten essay image (PNG, JPG, JPEG, or PDF)
2. **Select** OCR provider (currently "stub" only)
3. **Click** "Run Processor" to process the submission
4. **Review** extracted contact info and essay metrics
5. **Click** "Write to CSV" to export to appropriate CSV file

### Understanding Results

**Contact Information:**
- Student Name
- School Name
- Grade (numeric)
- Teacher Name (optional)
- City/Location (optional)

**Essay Metrics:**
- Word count
- OCR confidence score
- Validation status

**Validation Flags:**

Records needing review are flagged with reason codes:
- `MISSING_NAME` - Student name not found
- `MISSING_SCHOOL` - School name not found
- `MISSING_GRADE` - Grade not found
- `EMPTY_ESSAY` - No essay text detected
- `SHORT_ESSAY` - Essay under 50 words
- `LOW_CONFIDENCE` - OCR confidence below 50%

### Output Files

**CSV Files** (in `outputs/` directory):
- `submissions_clean.csv` - Complete, validated submissions
- `submissions_needs_review.csv` - Submissions requiring manual review

**Artifacts** (in `artifacts/[submission_id]/` directory):
- `original.[ext]` - Uploaded file
- `ocr.json` - Raw OCR results
- `raw_text.txt` - Full extracted text
- `contact_block.txt` - Separated contact section
- `essay_block.txt` - Separated essay content
- `structured.json` - Extracted fields and metrics
- `validation.json` - Validation report

## Architecture

### Modular Design

Each pipeline stage is isolated and testable:

```python
# Pipeline flow
ingest → OCR → segment → extract → validate → CSV export
```

### Data Models (Pydantic)

**SubmissionRecord:**
- Contact fields (name, school, grade, etc.)
- Essay metrics (word count, confidence)
- Validation flags and reason codes
- Artifact tracking

**OcrResult:**
- Extracted text
- Confidence scores
- Line-by-line breakdown

### OCR Provider Pattern

Abstracted OCR interface allows easy integration of real providers:

```python
class OcrProvider(Protocol):
    def process_image(self, image_path: str) -> OcrResult:
        ...
```

Current stub provider simulates handwritten text for development.

## Current Limitations

- **Stub OCR Only** - Real OCR providers (Google Vision, Azure, Tesseract) not yet integrated
- **Single Page** - Only processes one-page submissions
- **English Only** - No multilingual support yet
- **Rule-Based Extraction** - Uses regex patterns, not ML-based extraction

## Next Steps

To integrate real OCR providers:

1. Implement new provider class in `pipeline/ocr.py`
2. Add provider to `get_ocr_provider()` factory
3. Update UI dropdown in `app.py`
4. Install provider-specific dependencies

Example structure:

```python
class GoogleVisionOcrProvider:
    def process_image(self, image_path: str) -> OcrResult:
        # Call Google Vision API
        ...
```

## Development

### Running Tests

(Tests not yet implemented)

```bash
pytest tests/
```

### Code Style

Follow PEP 8. Use type hints for all function signatures.

### Adding New Fields

1. Update `SubmissionRecord` in `pipeline/schema.py`
2. Add extraction logic in `pipeline/extract.py`
3. Update CSV headers in `pipeline/csv_writer.py`
4. Update UI display in `app.py`

## License

(Add your license here)

## Contact

(Add contact information)


