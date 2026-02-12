# Local DBF Testing Guide

This guide helps you test the DBF remediation changes locally against your Supabase database.

## Prerequisites

1. **Migration Applied**: You've already run `006_audit_tables.sql` on your Supabase database ✅
2. **Environment Variables**: Set up your `.env` file or export variables:
   ```bash
   export SUPABASE_URL=your_supabase_url
   export SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
   export SUPABASE_ANON_KEY=your_anon_key
   ```

## Quick Test Script

Run the automated test script:

```bash
cd "IFI Essay tool"
python test_dbf_local.py
```

This will test:
- ✅ Audit table insertion (traces and events)
- ✅ OCR_FAILED reason code (distinct from LOW_CONFIDENCE)
- ✅ Deterministic classification
- ✅ Escalation threshold (< 0.3)
- ✅ Audit trace structure

## Manual Testing Steps

### 1. Test Audit Trail Insertion

```python
from pipeline.supabase_audit import insert_audit_trace, insert_audit_event
from pipeline.audit import build_decision_trace

# Build a test trace
trace = build_decision_trace(
    submission_id="manual_test_001",
    filename="test.pdf",
    owner_user_id="your-user-id",
    ocr_result={"confidence_avg": 0.65, "text": "test", "lines": []},
    extracted_fields={"student_name": "Test Student"},
    validation_result={"needs_review": True},
    rules_applied=[{"rule_id": "test_rule", "result": False}]
)

# Insert trace
result = insert_audit_trace("manual_test_001", "your-user-id", trace)
print(f"Trace inserted: {result}")

# Insert event
result = insert_audit_event(
    submission_id="manual_test_001",
    actor_role="system",
    event_type="TEST_EVENT",
    event_payload={"test": True}
)
print(f"Event inserted: {result}")
```

**Verify in Supabase:**
```sql
-- Check traces
SELECT * FROM submission_audit_traces 
WHERE submission_id = 'manual_test_001'
ORDER BY created_at DESC;

-- Check events
SELECT * FROM submission_audit_events 
WHERE submission_id = 'manual_test_001'
ORDER BY created_at DESC;
```

### 2. Test OCR_FAILED vs LOW_CONFIDENCE

```python
from pipeline.validate import validate_record

# Test OCR_FAILED (actual failure)
record1, _ = validate_record({
    "submission_id": "test_001",
    "student_name": "John",
    "school_name": "Test",
    "grade": 5,
    "word_count": 100,
    "ocr_confidence_avg": 0.0,
    "ocr_failed": True,  # OCR actually failed
    "artifact_dir": "test"
})
print(f"OCR_FAILED: {'OCR_FAILED' in record1.review_reason_codes}")
print(f"Reason codes: {record1.review_reason_codes}")

# Test LOW_CONFIDENCE (OCR succeeded, just low confidence)
record2, _ = validate_record({
    "submission_id": "test_002",
    "student_name": "John",
    "school_name": "Test",
    "grade": 5,
    "word_count": 100,
    "ocr_confidence_avg": 0.4,  # Low confidence
    "ocr_failed": False,  # OCR succeeded
    "artifact_dir": "test"
})
print(f"LOW_CONFIDENCE: {'LOW_CONFIDENCE' in record2.review_reason_codes}")
print(f"OCR_FAILED: {'OCR_FAILED' in record2.review_reason_codes}")
print(f"Reason codes: {record2.review_reason_codes}")
```

**Expected:**
- `test_001`: Has `OCR_FAILED`, no `LOW_CONFIDENCE`
- `test_002`: Has `LOW_CONFIDENCE`, no `OCR_FAILED`

### 3. Test Deterministic Classification

```python
from pipeline.classify import extract_classification_features, verify_doc_type_signal

ocr_text = """Student's Name: John Doe
School: Test School
Grade: 5

What my father means to me..."""

# Extract features (should be deterministic)
features1 = extract_classification_features(ocr_text)
features2 = extract_classification_features(ocr_text)
print(f"Features match: {features1 == features2}")

# Verify LLM signal
signal = "IFI_OFFICIAL_FORM_FILLED"
doc_type1, verified1, _ = verify_doc_type_signal(signal, features1, ocr_text)
doc_type2, verified2, _ = verify_doc_type_signal(signal, features2, ocr_text)
print(f"Doc type deterministic: {doc_type1 == doc_type2}")
print(f"Doc type: {doc_type1}")
```

### 4. Test End-to-End Pipeline

Start Flask app:

```bash
cd "IFI Essay tool"
python flask_app.py
```

Then:
1. Upload a test PDF via the web UI
2. Check Supabase for audit trace and events:
   ```sql
   -- Get latest trace
   SELECT * FROM submission_audit_traces 
   ORDER BY created_at DESC LIMIT 1;
   
   -- Get all events for latest submission
   SELECT event_type, actor_role, event_payload, created_at 
   FROM submission_audit_events 
   WHERE submission_id = (
       SELECT submission_id FROM submission_audit_traces 
       ORDER BY created_at DESC LIMIT 1
   )
   ORDER BY created_at;
   ```

3. Verify events include:
   - `INGESTED`
   - `OCR_COMPLETE`
   - `EXTRACTION_COMPLETE`
   - `VALIDATION_COMPLETE`
   - `SAVED`

### 5. Test Approval Event

1. Approve a record via the web UI (`/record/<submission_id>/approve`)
2. Check for `APPROVED` event:
   ```sql
   SELECT * FROM submission_audit_events 
   WHERE event_type = 'APPROVED'
   ORDER BY created_at DESC LIMIT 1;
   ```

### 6. Test Duplicate Skip

1. Upload the same file twice
2. Check for `DUPLICATE_SKIPPED` event:
   ```sql
   SELECT * FROM submission_audit_events 
   WHERE event_type = 'DUPLICATE_SKIPPED'
   ORDER BY created_at DESC LIMIT 1;
   ```

## Verification Checklist

After testing, verify:

- [ ] Audit traces are inserted into `submission_audit_traces`
- [ ] Audit events are inserted into `submission_audit_events`
- [ ] `OCR_FAILED` appears when OCR errors occur (distinct from `LOW_CONFIDENCE`)
- [ ] `ESCALATED` appears when confidence < 0.3
- [ ] Approval creates `APPROVED` event
- [ ] Duplicate uploads create `DUPLICATE_SKIPPED` event
- [ ] Trace structure has: input, signals, rules_applied, outcome, errors
- [ ] Classification is deterministic (same input → same output)

## Troubleshooting

### Audit Insertion Fails

**Check:**
1. `SUPABASE_SERVICE_ROLE_KEY` is set correctly
2. Migration `006_audit_tables.sql` was applied
3. Tables exist: `submission_audit_traces`, `submission_audit_events`

**Verify tables:**
```sql
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name LIKE '%audit%';
```

### OCR_FAILED Not Appearing

**Check:**
1. `ocr_failed` flag is set in `OcrResult` when errors occur
2. `validate.py` checks `ocr_failed` before checking confidence
3. Reason codes include `OCR_FAILED`

### Events Not Appearing

**Check:**
1. `owner_user_id` is passed to `process_submission()`
2. `access_token` is available for authenticated inserts
3. Service role key has permissions to insert

## Next Steps

Once local testing passes:
1. Deploy to staging/production
2. Monitor audit trail in production
3. Verify events are being written correctly
4. Set up alerts for `ESCALATED` events
