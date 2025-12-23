# EssayFlow - Testing Guide

## Current Testing (Stub OCR)

### Manual Testing Workflow

#### 1. Basic Happy Path
```bash
# Start the app
streamlit run app.py

# Steps:
1. Upload any image file (content doesn't matter)
2. Select "stub" OCR provider
3. Click "Run Processor"
4. Verify extracted data:
   - Name: Andrick Vargas Hernandez
   - School: Lincoln Middle School
   - Grade: 8
   - Word Count: ~150
5. Click "Write to CSV"
6. Check outputs/submissions_clean.csv
```

#### 2. Verify Artifacts
```bash
# After processing, check artifact directory
ls -la artifacts/sub_*/

# Should contain:
# - original.[ext]
# - ocr.json
# - raw_text.txt
# - contact_block.txt
# - essay_block.txt
# - structured.json
# - validation.json

# Inspect each file
cat artifacts/sub_*/structured.json | python -m json.tool
```

#### 3. Test CSV Routing
```bash
# Check clean submissions
cat outputs/submissions_clean.csv

# Check needs review (should be empty with stub)
cat outputs/submissions_needs_review.csv

# Verify headers match schema
head -n 1 outputs/submissions_clean.csv
```

### Testing Individual Modules

#### Test Ingest
```python
from pipeline.ingest import ingest_upload

# Test with dummy bytes
test_bytes = b"fake image data"
result = ingest_upload(test_bytes, "test.png", "test_artifacts")

print(result["submission_id"])
print(result["artifact_dir"])
# Verify directory was created
```

#### Test OCR
```python
from pipeline.ocr import get_ocr_provider

provider = get_ocr_provider("stub")
result = provider.process_image("any_path.png")

print(result.text)
print(result.confidence_avg)
print(len(result.lines))
```

#### Test Segmentation
```python
from pipeline.segment import split_contact_vs_essay

sample_text = """Name: John Doe
School: Test School
Grade: 7

This is my essay about something important.
It has multiple paragraphs and sentences."""

contact, essay = split_contact_vs_essay(sample_text)
print("Contact:", contact)
print("Essay:", essay)
```

#### Test Extraction
```python
from pipeline.extract import extract_fields_rules, compute_essay_metrics

contact_block = """Name: Jane Smith
School: Example Middle School
Grade: 8
Teacher: Ms. Johnson"""

fields = extract_fields_rules(contact_block)
print(fields)

essay_block = "This is a test essay with some words."
metrics = compute_essay_metrics(essay_block)
print(metrics)
```

#### Test Validation
```python
from pipeline.validate import validate_record

partial = {
    "submission_id": "test_123",
    "student_name": "Test Student",
    "school_name": "Test School",
    "grade": 8,
    "word_count": 100,
    "ocr_confidence_avg": 0.75,
    "artifact_dir": "test_artifacts"
}

record, report = validate_record(partial)
print(record.needs_review)
print(report)
```

## Future Testing (Real OCR)

### Test Cases for Real OCR Integration

#### 1. Perfect Handwriting
- Clear, legible handwriting
- All fields present
- Expected: Clean extraction, no review needed

#### 2. Messy Handwriting
- Difficult to read
- Some fields unclear
- Expected: Lower confidence, possible review flag

#### 3. Missing Fields
- Name present, school missing
- Expected: MISSING_SCHOOL flag

#### 4. Incomplete Essay
- Contact info complete
- Essay only 20 words
- Expected: SHORT_ESSAY flag

#### 5. Wrong Layout
- Essay text at top
- Contact info at bottom
- Expected: Segmentation should handle gracefully

#### 6. Multiple Languages
- Mix of English and other languages
- Expected: Depends on OCR provider capabilities

#### 7. Poor Image Quality
- Blurry, low resolution
- Expected: LOW_CONFIDENCE flag

#### 8. Rotated Image
- Image rotated 90/180 degrees
- Expected: OCR provider should handle or flag

### Automated Testing Structure

```python
# tests/test_ingest.py
import pytest
from pipeline.ingest import ingest_upload

def test_ingest_creates_directory():
    result = ingest_upload(b"test", "test.png", "test_artifacts")
    assert "submission_id" in result
    assert os.path.exists(result["artifact_dir"])

def test_ingest_generates_unique_ids():
    r1 = ingest_upload(b"test1", "test1.png", "test_artifacts")
    r2 = ingest_upload(b"test2", "test2.png", "test_artifacts")
    assert r1["submission_id"] != r2["submission_id"]
```

```python
# tests/test_segment.py
import pytest
from pipeline.segment import split_contact_vs_essay

def test_segment_splits_correctly():
    text = "Name: John\nSchool: Test\n\nEssay text here."
    contact, essay = split_contact_vs_essay(text)
    assert "Name:" in contact
    assert "Essay" in essay

def test_segment_handles_no_break():
    text = "Name: John\nSchool: Test\nEssay text here."
    contact, essay = split_contact_vs_essay(text)
    assert len(contact) > 0
    assert len(essay) > 0
```

```python
# tests/test_extract.py
import pytest
from pipeline.extract import extract_fields_rules

def test_extract_all_fields():
    contact = "Name: John Doe\nSchool: Test School\nGrade: 7"
    fields = extract_fields_rules(contact)
    assert fields["student_name"] == "John Doe"
    assert fields["school_name"] == "Test School"
    assert fields["grade"] == 7

def test_extract_handles_missing_fields():
    contact = "Name: John Doe"
    fields = extract_fields_rules(contact)
    assert fields["student_name"] == "John Doe"
    assert fields["school_name"] is None
```

```python
# tests/test_validate.py
import pytest
from pipeline.validate import validate_record

def test_validate_complete_record():
    partial = {
        "submission_id": "test",
        "student_name": "John",
        "school_name": "School",
        "grade": 8,
        "word_count": 100,
        "artifact_dir": "test"
    }
    record, report = validate_record(partial)
    assert not record.needs_review
    assert report["is_valid"]

def test_validate_missing_name():
    partial = {
        "submission_id": "test",
        "school_name": "School",
        "grade": 8,
        "word_count": 100,
        "artifact_dir": "test"
    }
    record, report = validate_record(partial)
    assert record.needs_review
    assert "MISSING_NAME" in record.review_reason_codes
```

### Integration Testing

```python
# tests/test_integration.py
import pytest
from pipeline.runner import process_submission
from pipeline.ingest import ingest_upload

def test_full_pipeline():
    # Ingest
    result = ingest_upload(b"test", "test.png", "test_artifacts")
    
    # Process
    record, report = process_submission(
        image_path=result["saved_path"],
        submission_id=result["submission_id"],
        artifact_dir=result["artifact_dir"],
        ocr_provider_name="stub"
    )
    
    # Verify
    assert record.submission_id == result["submission_id"]
    assert record.student_name is not None
    assert record.word_count > 0
    assert os.path.exists(f"{result['artifact_dir']}/ocr.json")
    assert os.path.exists(f"{result['artifact_dir']}/validation.json")
```

### Performance Testing

```python
# tests/test_performance.py
import time
import pytest
from pipeline.runner import process_submission

def test_processing_speed():
    start = time.time()
    
    # Process 10 submissions
    for i in range(10):
        result = ingest_upload(f"test{i}".encode(), f"test{i}.png")
        record, report = process_submission(
            result["saved_path"],
            result["submission_id"],
            result["artifact_dir"]
        )
    
    elapsed = time.time() - start
    avg_time = elapsed / 10
    
    # With stub OCR, should be very fast
    assert avg_time < 0.5  # 500ms per submission
```

### Edge Cases

#### Empty/Corrupt Images
```python
def test_corrupt_image():
    # Test with corrupt image data
    # Should handle gracefully
    pass
```

#### Extremely Long Essays
```python
def test_long_essay():
    # Test with 1000+ word essay
    # Should process without issues
    pass
```

#### Special Characters
```python
def test_special_characters():
    # Test with names containing accents, hyphens
    # Should preserve correctly
    pass
```

#### Duplicate Submissions
```python
def test_duplicate_submission():
    # Same image uploaded twice
    # Should create separate records with unique IDs
    pass
```

## Test Data Preparation

### Sample Images Needed

1. **Perfect Sample** - Clear handwriting, all fields
2. **Messy Sample** - Difficult handwriting
3. **Missing Fields** - Some fields blank
4. **Short Essay** - Under 50 words
5. **Long Essay** - 500+ words
6. **Poor Quality** - Blurry, low resolution
7. **Rotated** - 90° rotation
8. **Different Layouts** - Variations in field order

### Creating Test Images

```python
# Use PIL to generate test images with text
from PIL import Image, ImageDraw, ImageFont

def create_test_image(text_lines, filename):
    img = Image.new('RGB', (800, 1000), color='white')
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    
    y = 50
    for line in text_lines:
        draw.text((50, y), line, fill='black', font=font)
        y += 30
    
    img.save(filename)
```

## Continuous Testing

### Pre-commit Checks
```bash
# Run before committing
python -m pytest tests/
python -m pylint pipeline/
python -m mypy pipeline/
```

### CI/CD Pipeline
```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -r requirements.txt pytest
      - run: pytest tests/
```

## Monitoring in Production

### Metrics to Track
- Processing time per submission
- OCR confidence distribution
- Review rate (% needing review)
- Most common review reasons
- Field extraction success rates

### Logging
```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In pipeline stages
logger.info(f"Processing submission {submission_id}")
logger.warning(f"Low confidence: {confidence}")
logger.error(f"Failed to extract field: {field_name}")
```

## Troubleshooting

### Common Issues

**Issue**: All submissions flagged for review  
**Check**: Validation thresholds, OCR confidence

**Issue**: Segmentation always splits at same line  
**Check**: Anchor word detection, line counting logic

**Issue**: Fields not extracted  
**Check**: Regex patterns, OCR text format

**Issue**: CSV corruption  
**Check**: Header consistency, encoding issues

## Next Steps

1. Set up pytest framework
2. Create test image dataset
3. Implement unit tests for each module
4. Add integration tests
5. Set up CI/CD pipeline
6. Add performance benchmarks
7. Create monitoring dashboard

