# EssayFlow Architecture

## Pipeline Overview

```
┌─────────────┐
│   Upload    │  User uploads handwritten essay image
│   (app.py)  │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│                    PIPELINE STAGES                       │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────┐
│  1. INGEST  │  • Generate submission_id
│ (ingest.py) │  • Create artifact directory
└──────┬──────┘  • Save uploaded file
       │
       ▼
┌─────────────┐
│   2. OCR    │  • Extract text from image
│  (ocr.py)   │  • Compute confidence scores
└──────┬──────┘  • Split into lines
       │          Artifact: ocr.json, raw_text.txt
       ▼
┌─────────────┐
│ 3. SEGMENT  │  • Identify contact section (top)
│(segment.py) │  • Separate essay body (main)
└──────┬──────┘  • Use anchor words & line position
       │          Artifacts: contact_block.txt, essay_block.txt
       ▼
┌─────────────┐
│ 4. EXTRACT  │  • Parse contact fields (regex)
│(extract.py) │  • Compute essay metrics (word count)
└──────┬──────┘  • Handle optional fields
       │          Artifact: structured.json
       ▼
┌─────────────┐
│ 5. VALIDATE │  • Check required fields
│(validate.py)│  • Flag quality issues
└──────┬──────┘  • Set review codes
       │          Artifact: validation.json
       ▼
┌─────────────┐
│  6. EXPORT  │  • Route to appropriate CSV
│(csv_writer) │  • Append with frozen headers
└──────┬──────┘  • Track statistics
       │
       ▼
┌─────────────────────────────────┐
│  submissions_clean.csv          │  Complete records
│  submissions_needs_review.csv   │  Flagged records
└─────────────────────────────────┘
```

## Data Flow

### Input
```
Handwritten Essay Image
├── Contact Section (top, 3-10 lines)
│   ├── Name: [handwritten]
│   ├── School: [handwritten]
│   ├── Grade: [handwritten]
│   └── Optional: Teacher, Location
└── Essay Body (main content)
    └── Free-form handwritten text
```

### Processing
```
Raw Image
    ↓ OCR
Raw Text (confidence ~65%)
    ↓ Segmentation
Contact Block + Essay Block
    ↓ Extraction
Structured Fields + Metrics
    ↓ Validation
SubmissionRecord (validated)
    ↓ CSV Export
Persistent Storage
```

### Output
```
SubmissionRecord
├── submission_id: "sub_20231223_143052_a1b2c3d4"
├── student_name: "Andrick Vargas Hernandez"
├── school_name: "Lincoln Middle School"
├── grade: 8
├── teacher_name: null (optional)
├── city_or_location: null (optional)
├── word_count: 152
├── ocr_confidence_avg: 0.65
├── needs_review: false
├── review_reason_codes: ""
└── artifact_dir: "artifacts/sub_20231223_143052_a1b2c3d4"
```

## Module Responsibilities

### `schema.py` - Data Models
- **SubmissionRecord**: Complete submission with all fields
- **OcrResult**: Raw OCR output with metadata
- Uses Pydantic for validation and type safety

### `ingest.py` - File Handling
- Accepts uploaded bytes
- Generates unique submission IDs
- Creates artifact directory structure
- Saves original file

### `ocr.py` - Text Extraction
- **OcrProvider Protocol**: Interface for OCR providers
- **StubOcrProvider**: Simulates handwritten text
- **get_ocr_provider()**: Factory function
- Returns structured OcrResult

### `segment.py` - Text Segmentation
- Splits raw text into contact vs. essay
- Uses anchor word detection ("Name:", "School:", etc.)
- Handles inconsistent layouts
- Early-line bias for contact section

### `extract.py` - Field Parsing
- **extract_fields_rules()**: Regex-based contact parsing
- **compute_essay_metrics()**: Word count, char count, paragraphs
- Handles missing/illegible fields gracefully
- Returns structured dictionaries

### `validate.py` - Quality Control
- Checks required fields (name, school, grade)
- Validates essay content (length, presence)
- Checks OCR confidence thresholds
- Sets review flags and reason codes

### `csv_writer.py` - Persistence
- Frozen CSV headers (consistent schema)
- Safe append operations
- Dual routing (clean vs. needs review)
- Statistics tracking

### `runner.py` - Orchestration
- Coordinates all pipeline stages
- Writes artifacts at each step
- Generates processing reports
- Returns validated SubmissionRecord

### `app.py` - User Interface
- Streamlit-based web UI
- File upload handling
- Real-time processing feedback
- Results display and CSV export

## Validation Rules

### Required Fields
- `student_name` must be present
- `school_name` must be present
- `grade` must be present and numeric
- `word_count` must be > 0

### Quality Checks
- Essay must be ≥ 50 words (else `SHORT_ESSAY`)
- OCR confidence ≥ 50% (else `LOW_CONFIDENCE`)

### Review Reason Codes
- `MISSING_NAME` - Student name not extracted
- `MISSING_SCHOOL` - School name not extracted
- `MISSING_GRADE` - Grade not extracted
- `EMPTY_ESSAY` - No essay text found
- `SHORT_ESSAY` - Essay under 50 words
- `LOW_CONFIDENCE` - OCR confidence < 50%

Multiple codes are joined with semicolons: `MISSING_NAME;SHORT_ESSAY`

## Artifact Structure

Each submission generates a complete audit trail:

```
artifacts/sub_20231223_143052_a1b2c3d4/
├── original.png              # Original upload
├── ocr.json                  # Raw OCR output
│   └── {text, confidence_avg, lines[]}
├── raw_text.txt              # Full extracted text
├── contact_block.txt         # Segmented contact section
├── essay_block.txt           # Segmented essay content
├── structured.json           # Extracted fields + metrics
│   └── {name, school, grade, word_count, ...}
└── validation.json           # Validation report
    └── {is_valid, needs_review, issues[], ...}
```

## Extension Points

### Adding New OCR Providers

```python
# In pipeline/ocr.py
class GoogleVisionOcrProvider:
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def process_image(self, image_path: str) -> OcrResult:
        # Call Google Vision API
        # Parse response
        # Return OcrResult
        pass

# Update factory
def get_ocr_provider(name: str, **kwargs) -> OcrProvider:
    if name == "stub":
        return StubOcrProvider()
    elif name == "google_vision":
        return GoogleVisionOcrProvider(kwargs["api_key"])
    # ...
```

### Adding New Fields

1. Update `SubmissionRecord` in `schema.py`
2. Add extraction logic in `extract.py`
3. Update CSV headers in `csv_writer.py`
4. Update validation rules in `validate.py` (if required)
5. Update UI display in `app.py`

### Adding ML-Based Extraction

Replace rule-based extraction in `extract.py`:

```python
def extract_fields_ml(contact_block: str, model) -> dict:
    # Use NER model or LLM
    # Extract structured fields
    # Return dict
    pass
```

## Design Principles

1. **Modularity**: Each stage is independent and testable
2. **Transparency**: Full artifact trail for debugging
3. **Graceful Degradation**: Missing fields don't break pipeline
4. **Type Safety**: Pydantic models enforce schema
5. **Extensibility**: Easy to add new providers/fields
6. **Production-Ready**: Proper error handling and validation

## Performance Considerations

- **Stub OCR**: Instant (no actual processing)
- **Real OCR**: 2-5 seconds per page (provider-dependent)
- **Segmentation**: < 10ms (regex-based)
- **Extraction**: < 10ms (regex-based)
- **Validation**: < 1ms (rule-based)
- **CSV Write**: < 10ms (append operation)

**Total**: ~3-6 seconds per submission with real OCR

## Future Enhancements

- [ ] Multi-page support
- [ ] Batch processing
- [ ] ML-based field extraction
- [ ] Confidence-based field highlighting
- [ ] Manual correction interface
- [ ] Export to additional formats (JSON, Excel)
- [ ] Analytics dashboard
- [ ] API endpoints (REST/GraphQL)

