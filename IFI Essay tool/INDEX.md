# EssayFlow - Documentation Index

Complete guide to the EssayFlow handwritten essay processing system.

## 📚 Documentation Files

### Getting Started
1. **[QUICKSTART.md](QUICKSTART.md)** ⭐ START HERE
   - 3-minute setup guide
   - First submission walkthrough
   - Basic troubleshooting

2. **[README.md](README.md)**
   - Project overview
   - Features and capabilities
   - Setup instructions
   - Usage guide

### Technical Documentation
3. **[ARCHITECTURE.md](ARCHITECTURE.md)**
   - Pipeline architecture
   - Data flow diagrams
   - Module responsibilities
   - Design principles
   - Extension points

4. **[PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)**
   - What was built
   - File structure
   - Key features
   - Data models
   - Next steps

5. **[TESTING_GUIDE.md](TESTING_GUIDE.md)**
   - Manual testing procedures
   - Automated test structure
   - Test cases for real OCR
   - Performance testing
   - Edge cases

## 🗂️ Source Code Files

### Main Application
- **`app.py`** - Streamlit web interface
  - File upload handling
  - Processing workflow
  - Results display
  - CSV export UI

### Pipeline Modules (`pipeline/`)

#### Core Data Models
- **`schema.py`** - Pydantic models
  - `SubmissionRecord` - Complete submission data
  - `OcrResult` - OCR output structure

#### Processing Stages
- **`ingest.py`** - File ingestion
  - Upload handling
  - Submission ID generation
  - Artifact directory creation

- **`ocr.py`** - Text extraction
  - OCR provider protocol
  - Stub OCR implementation
  - Provider factory function

- **`segment.py`** - Text segmentation
  - Contact/essay separation
  - Anchor word detection
  - Layout heuristics

- **`extract.py`** - Field extraction
  - Contact field parsing (regex)
  - Essay metrics computation
  - Optional field handling

- **`validate.py`** - Data validation
  - Required field checking
  - Quality validation
  - Review flag logic

- **`csv_writer.py`** - Data persistence
  - CSV export with frozen headers
  - Dual routing (clean vs review)
  - Statistics tracking

- **`runner.py`** - Pipeline orchestration
  - Stage coordination
  - Artifact generation
  - Processing reports

### Configuration
- **`requirements.txt`** - Python dependencies
- **`.gitignore`** - Git exclusions

## 📁 Directory Structure

```
essayflow/
├── Documentation (you are here)
│   ├── INDEX.md              # This file
│   ├── QUICKSTART.md         # Quick start
│   ├── README.md             # Main docs
│   ├── ARCHITECTURE.md       # Technical details
│   ├── PROJECT_SUMMARY.md    # Overview
│   └── TESTING_GUIDE.md      # Testing
│
├── Application
│   └── app.py                # Streamlit UI
│
├── Pipeline (core logic)
│   └── pipeline/
│       ├── schema.py         # Data models
│       ├── ingest.py         # Ingestion
│       ├── ocr.py            # OCR
│       ├── segment.py        # Segmentation
│       ├── extract.py        # Extraction
│       ├── validate.py       # Validation
│       ├── csv_writer.py     # Export
│       └── runner.py         # Orchestration
│
├── Configuration
│   ├── requirements.txt      # Dependencies
│   └── .gitignore           # Git rules
│
└── Runtime (generated)
    ├── artifacts/            # Processing artifacts
    └── outputs/              # CSV exports
```

## 🚀 Quick Navigation

### I want to...

**Get started quickly**
→ [QUICKSTART.md](QUICKSTART.md)

**Understand the architecture**
→ [ARCHITECTURE.md](ARCHITECTURE.md)

**See what was built**
→ [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)

**Learn about testing**
→ [TESTING_GUIDE.md](TESTING_GUIDE.md)

**Read full documentation**
→ [README.md](README.md)

**Modify the code**
→ Start with `pipeline/schema.py` to understand data models
→ Then review `pipeline/runner.py` for pipeline flow

**Add a new OCR provider**
→ See "Adding New OCR Providers" in [ARCHITECTURE.md](ARCHITECTURE.md)

**Add a new field**
→ See "Adding New Fields" in [ARCHITECTURE.md](ARCHITECTURE.md)

**Debug an issue**
→ Check artifacts in `artifacts/[submission_id]/`
→ Review [TESTING_GUIDE.md](TESTING_GUIDE.md) troubleshooting section

## 📊 Data Flow Reference

```
Upload → Ingest → OCR → Segment → Extract → Validate → Export
  ↓        ↓       ↓       ↓         ↓         ↓         ↓
Image   Metadata  Text   Blocks   Fields   Record    CSV
```

## 🔑 Key Concepts

### Submission Record
Complete data for one essay submission including contact info, metrics, and validation status.

### Artifacts
JSON and text files generated at each pipeline stage for debugging and audit trails.

### Validation Flags
Automatic quality checks that route submissions to "clean" or "needs review" CSV files.

### OCR Provider
Abstraction layer for text extraction - currently stub, ready for real OCR integration.

### Review Reason Codes
Semicolon-separated codes indicating why a submission needs manual review:
- `MISSING_NAME`, `MISSING_SCHOOL`, `MISSING_GRADE`
- `EMPTY_ESSAY`, `SHORT_ESSAY`
- `LOW_CONFIDENCE`

## 🎯 Common Tasks

### Run the Application
```bash
streamlit run app.py
```

### Process a Submission
1. Upload image
2. Click "Run Processor"
3. Review results
4. Click "Write to CSV"

### Check Artifacts
```bash
ls artifacts/sub_*/
cat artifacts/sub_*/structured.json
```

### View CSV Output
```bash
cat outputs/submissions_clean.csv
cat outputs/submissions_needs_review.csv
```

### Test Individual Module
```python
from pipeline.segment import split_contact_vs_essay
contact, essay = split_contact_vs_essay(text)
```

## 🔧 Development Workflow

1. **Setup**: Follow [QUICKSTART.md](QUICKSTART.md)
2. **Understand**: Read [ARCHITECTURE.md](ARCHITECTURE.md)
3. **Modify**: Edit pipeline modules
4. **Test**: Use [TESTING_GUIDE.md](TESTING_GUIDE.md)
5. **Run**: `streamlit run app.py`
6. **Debug**: Check artifacts directory

## 📖 Code Reading Order

For new developers, read code in this order:

1. `pipeline/schema.py` - Understand data structures
2. `pipeline/runner.py` - See overall pipeline flow
3. `pipeline/ingest.py` - Simple starting point
4. `pipeline/ocr.py` - OCR abstraction
5. `pipeline/segment.py` - Text processing
6. `pipeline/extract.py` - Field parsing
7. `pipeline/validate.py` - Validation logic
8. `pipeline/csv_writer.py` - Export logic
9. `app.py` - UI integration

## 🐛 Debugging Checklist

1. Check terminal output for errors
2. Review artifacts in `artifacts/[submission_id]/`
3. Inspect `validation.json` for issues
4. Check CSV files in `outputs/`
5. Verify all pipeline stages completed
6. Review [TESTING_GUIDE.md](TESTING_GUIDE.md) troubleshooting

## 📝 Contributing

When adding features:

1. Update data models in `schema.py` if needed
2. Add processing logic to appropriate module
3. Update validation rules if needed
4. Update CSV headers if adding fields
5. Update UI in `app.py`
6. Document in relevant .md file
7. Add tests (see [TESTING_GUIDE.md](TESTING_GUIDE.md))

## 🎓 Learning Resources

### Python Concepts Used
- Pydantic for data validation
- Type hints and protocols
- Pathlib for file operations
- Context managers (with statements)
- List comprehensions

### Streamlit Concepts
- File uploaders
- Session state
- Columns and layout
- Buttons and interactions
- Status indicators

### Design Patterns
- Protocol/Interface pattern (OCR providers)
- Factory pattern (get_ocr_provider)
- Pipeline pattern (staged processing)
- Strategy pattern (validation rules)

## 📞 Support

For issues or questions:

1. Check [QUICKSTART.md](QUICKSTART.md) troubleshooting
2. Review [TESTING_GUIDE.md](TESTING_GUIDE.md) common issues
3. Inspect artifacts for debugging
4. Check documentation for relevant section

## 🗺️ Roadmap

See "Future Enhancements" in [ARCHITECTURE.md](ARCHITECTURE.md):
- Multi-page support
- Batch processing
- ML-based extraction
- Manual review interface
- Analytics dashboard
- API endpoints

---

**Last Updated**: December 2023  
**Version**: 1.0 (Stub OCR Skeleton)  
**Status**: Complete and Ready for OCR Integration


