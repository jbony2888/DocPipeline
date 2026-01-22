# Multi-Entry PDF Detection and Splitting

## Overview

The system automatically detects and splits PDFs containing multiple student submissions into separate records. This handles batch-scanned submissions where schools scan multiple essays into a single PDF file.

## Problem

Schools sometimes batch-scan multiple student entries into a single PDF:
- **Entry 1**: Page 1 (metadata/contact) + Page 2 (essay)
- **Entry 2**: Page 3 (metadata/contact) + Page 4 (essay)
- **Entry N**: ...

Previously, the system only processed the first page, losing all subsequent entries.

## Solution

### Automatic Detection

When a PDF is uploaded, the system:

1. **Analyzes page structure** using lightweight text extraction (no OCR cost)
2. **Classifies each page** as "metadata" or "essay" based on:
   - Metadata pages: short lines, form keywords (Name, Grade, School, Phone, Email)
   - Essay pages: longer paragraphs, narrative content
3. **Detects patterns**:
   - `metadata_essay`: Pages 0-1, 2-3, 4-5... (metadata on even, essay on odd)
   - `essay_metadata`: Pages 0-1, 2-3, 4-5... (essay on even, metadata on odd)
4. **Calculates confidence** based on pattern consistency

### Splitting Logic

If multi-entry is detected with confidence >= 0.7:

1. **Split PDF** into separate files (one per entry)
2. **Create N submission records** (each linked to parent upload)
3. **Process each record** through the full pipeline:
   - OCR (Google Vision)
   - Segmentation
   - LLM extraction (Groq)
   - Validation
   - Storage (Supabase)
   - Review workflow

### Safety Mechanisms

- **Confidence threshold**: Only splits if confidence >= 0.7
- **Fail-safe**: If uncertain, treats as single-entry (no data loss)
- **Single-entry unchanged**: PDFs with 1-2 pages always treated as single-entry
- **Odd page counts**: Treated as single-entry (ambiguous)

## Implementation

### Core Module

`pipeline/pdf_splitter.py` provides:

```python
from pipeline.pdf_splitter import analyze_pdf_structure, should_split_pdf

# Analyze PDF
analysis = analyze_pdf_structure(pdf_path)

# Check if should split
if should_split_pdf(analysis):
    # Split into separate files
    artifacts = split_pdf_into_groups(
        pdf_path=pdf_path,
        groups=analysis.detected_groups,
        output_dir=output_dir,
        base_filename=base_filename
    )
```

### Integration

`jobs/process_submission.py` automatically:

1. Detects multi-entry PDFs on upload
2. Splits into separate files
3. Enqueues processing jobs for each entry
4. Links child records to parent via `parent_submission_id`

### Database Fields

Child records include:

- `parent_submission_id`: ID of original upload
- `split_group_index`: Index of this entry (0-based)
- `multi_entry_source`: Boolean flag (true for split entries)

## Examples

### Single-Entry PDF (2 pages)

```
Page 0: Student metadata
Page 1: Essay text
```

**Result**: 1 record created (normal processing)

### Multi-Entry PDF (4 pages)

```
Page 0: Alice metadata
Page 1: Alice essay
Page 2: Bob metadata
Page 3: Bob essay
```

**Result**: 2 records created
- Record 1: Pages 0-1 (Alice)
- Record 2: Pages 2-3 (Bob)

### Multi-Entry PDF (6 pages)

```
Page 0: Alice metadata
Page 1: Alice essay
Page 2: Bob metadata
Page 3: Bob essay
Page 4: Carol metadata
Page 5: Carol essay
```

**Result**: 3 records created
- Record 1: Pages 0-1 (Alice)
- Record 2: Pages 2-3 (Bob)
- Record 3: Pages 4-5 (Carol)

## Testing

### Unit Tests

`tests/test_pdf_splitter.py` includes:

- Page classification tests
- Pattern detection tests
- Boundary detection tests
- Full PDF analysis tests
- Splitting functionality tests
- Edge case handling

Run tests:

```bash
pytest tests/test_pdf_splitter.py -v
```

### Manual Testing

```python
from pipeline.pdf_splitter import analyze_pdf_structure

# Analyze a PDF
analysis = analyze_pdf_structure("path/to/multi-entry.pdf")

print(f"Pages: {analysis.page_count}")
print(f"Multi-entry: {analysis.is_multi_entry}")
print(f"Confidence: {analysis.confidence:.2f}")
print(f"Groups: {analysis.detected_groups}")
```

## Performance

- **Text extraction**: Fast (PyMuPDF embedded text, no OCR)
- **Detection**: < 1 second for typical PDFs
- **Splitting**: < 1 second per PDF
- **No extra API costs**: Uses local text extraction, not OCR

## Limitations

1. **Pattern-based**: Assumes consistent 2-page entries
2. **Even page counts**: Odd-page PDFs (>3) treated as single-entry
3. **Text required**: Scanned images with no embedded text may not classify correctly
4. **Confidence threshold**: May miss some multi-entry PDFs with unusual layouts

## Future Enhancements

1. **Variable entry lengths**: Support 1-page or 3-page entries
2. **Visual analysis**: Use page layout/structure for classification
3. **Manual split UI**: Allow users to manually split ambiguous PDFs
4. **Batch summary emails**: Single email for all entries in a multi-entry PDF

## Troubleshooting

### PDF not splitting when expected

Check analysis results:

```python
analysis = analyze_pdf_structure(pdf_path)
print(f"Confidence: {analysis.confidence}")
print(f"Groups: {analysis.detected_groups}")
```

If confidence < 0.7, the system won't split automatically.

### Incorrect split boundaries

Review page classifications:

```python
from pipeline.pdf_splitter import _classify_page

for i, text in enumerate(analysis.pages_text):
    page_type = _classify_page(text)
    print(f"Page {i}: {page_type}")
```

Adjust classification heuristics in `_classify_page()` if needed.

### Single-entry PDF incorrectly split

This should not happen (fail-safe design). If it does:
1. Check confidence score (should be < 0.7 for ambiguous PDFs)
2. Review pattern detection logic in `_detect_page_pattern()`
3. File a bug report with the PDF

## Logging

The system logs:

```
INFO: Analyzing PDF for multi-entry detection: filename.pdf
INFO: Multi-entry PDF detected: filename.pdf (3 entries, confidence=0.85)
INFO: Created split PDF: filename_entry_1.pdf (pages 0-1)
INFO: Created split PDF: filename_entry_2.pdf (pages 2-3)
INFO: Created split PDF: filename_entry_3.pdf (pages 4-5)
```

Check logs for detection decisions and split results.
