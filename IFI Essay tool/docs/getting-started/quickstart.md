# EssayFlow - Quick Start Guide

Get up and running in 3 minutes.

## Installation

```bash
# Navigate to project directory
cd essayflow

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Run the Application

```bash
streamlit run app.py
```

The app will open automatically at `http://localhost:8501`

## First Submission

1. **Upload** any image file (the stub OCR will generate sample handwritten text)
2. **Click** "Run Processor"
3. **Review** the extracted data:
   - Name: Andrick Vargas Hernandez
   - School: Lincoln Middle School
   - Grade: 8
   - Word Count: ~150 words
4. **Click** "Write to CSV"
5. **Check** `outputs/submissions_clean.csv` for the exported record

## Understanding the Output

### Artifacts Directory

Each submission creates a folder in `artifacts/` with:

```
artifacts/sub_20231223_143052_a1b2c3d4/
├── original.png           # Uploaded file
├── ocr.json              # Raw OCR output
├── raw_text.txt          # Full extracted text
├── contact_block.txt     # Contact section only
├── essay_block.txt       # Essay content only
├── structured.json       # Parsed fields + metrics
└── validation.json       # Validation report
```

### CSV Files

Two CSV files are maintained in `outputs/`:

- **submissions_clean.csv** - Validated, complete submissions
- **submissions_needs_review.csv** - Submissions with missing/invalid data

### CSV Columns

```
submission_id, student_name, school_name, grade, teacher_name, 
city_or_location, word_count, ocr_confidence_avg, 
review_reason_codes, artifact_dir
```

## Testing with Real Images

The stub OCR ignores the actual image content and returns sample text. To test with real handwritten images:

1. Upload any image (content doesn't matter for stub)
2. The stub will return consistent sample output
3. The pipeline will process it as if it were real OCR

## Next Steps

- Review the modular pipeline in `pipeline/` directory
- Check `README.md` for architecture details
- Integrate real OCR provider (Google Vision, Azure, Tesseract)

## Troubleshooting

**Port already in use:**
```bash
streamlit run app.py --server.port 8502
```

**Module not found:**
```bash
# Ensure virtual environment is activated
source .venv/bin/activate
pip install -r requirements.txt
```

**Permission errors on artifacts/outputs:**
```bash
# Ensure directories exist and are writable
mkdir -p artifacts outputs
chmod 755 artifacts outputs
```

## Deactivate Virtual Environment

When done:
```bash
deactivate
```


