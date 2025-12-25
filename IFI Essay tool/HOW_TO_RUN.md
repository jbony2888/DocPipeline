# How to Run EssayFlow

## ✅ Setup Complete!

Your virtual environment is already set up with all dependencies installed.

## Running the Application

### Option 1: Quick Start (Recommended)

```bash
cd /Users/jerrybony/Documents/GitHub/DocPipeline/essayflow
source .venv/bin/activate
streamlit run app.py
```

### Option 2: Step-by-Step

1. **Navigate to the project directory:**
   ```bash
   cd /Users/jerrybony/Documents/GitHub/DocPipeline/essayflow
   ```

2. **Activate the virtual environment:**
   ```bash
   source .venv/bin/activate
   ```
   
   You should see `(.venv)` appear in your terminal prompt.

3. **Run the Streamlit app:**
   ```bash
   streamlit run app.py
   ```

4. **Access the application:**
   - Streamlit will automatically open your browser to `http://localhost:8501`
   - If it doesn't open automatically, navigate to that URL manually

## Using the Application

1. **Upload a file:**
   - Click "Browse files" or drag and drop
   - Supported formats: PNG, JPG, JPEG, PDF

2. **Click "Run Processor":**
   - The system will generate a deterministic `submission_id` based on file contents
   - You'll see the submission ID and artifact directory displayed
   - Processing happens through the pipeline (OCR → Segmentation → Extraction → Validation)

3. **Review results:**
   - View extracted contact information
   - Check essay metrics (word count, etc.)
   - See validation status
   - Expand "Artifact Details" to see generated files

4. **Export to CSV:**
   - Click "Write to CSV" to save the record
   - Records are automatically split into "clean" and "needs review" files

## What Happens Behind the Scenes

When you upload a file:

1. **Ingestion** (`pipeline/ingest.py`):
   - Computes SHA256 hash of file contents
   - Creates `submission_id` from first 12 chars (e.g., `8be5f83cc111`)
   - Creates `artifacts/{submission_id}/` directory
   - Saves file as `original.<ext>`
   - Writes `metadata.json` with full details

2. **Processing** (`pipeline/runner.py`):
   - Runs stub OCR (simulates handwritten text)
   - Segments contact info vs essay content
   - Extracts structured fields
   - Validates data quality
   - Writes artifacts at each stage

3. **Artifacts Created:**
   ```
   artifacts/{submission_id}/
   ├── metadata.json          # Ingestion metadata
   ├── original.<ext>         # Your uploaded file
   ├── ocr.json              # OCR results
   ├── raw_text.txt          # Full extracted text
   ├── contact_block.txt     # Contact section
   ├── essay_block.txt       # Essay content
   ├── structured.json       # Extracted fields
   └── validation.json       # Validation report
   ```

## Testing Deterministic Behavior

Upload the same file twice - you'll get the **same submission_id** both times! This prevents duplicate processing.

## Stopping the Application

Press `Ctrl+C` in the terminal where Streamlit is running.

## Deactivating the Virtual Environment

When you're done:
```bash
deactivate
```

## Troubleshooting

### Port Already in Use
If port 8501 is busy:
```bash
streamlit run app.py --server.port 8502
```

### Virtual Environment Not Activated
Make sure you see `(.venv)` in your prompt. If not:
```bash
source .venv/bin/activate
```

### Dependencies Missing
If you get import errors:
```bash
pip install -r requirements.txt
```

## Current Limitations

- **Stub OCR only**: Currently simulates handwritten text extraction
- **Single file processing**: Batch processing not yet implemented
- **Local only**: No cloud storage or API integration

## Next Steps

This implementation covers:
- ✅ Deterministic ingestion
- ✅ Artifact creation
- ✅ Local file processing
- ✅ Streamlit UI

Future enhancements:
- Real OCR integration (Azure, Google Vision, etc.)
- Batch processing workers
- Cloud storage support
- Enhanced validation rules

---

**Need Help?** Check the other documentation files:
- `QUICKSTART.md` - Project overview
- `ARCHITECTURE.md` - System design
- `TESTING_GUIDE.md` - Testing instructions
- `INGEST_IMPLEMENTATION.md` - Details on ingestion system


