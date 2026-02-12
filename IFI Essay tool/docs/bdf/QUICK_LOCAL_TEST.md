# Quick Local DBF Test

## ✅ Test Results

Your local test shows:
- ✅ OCR_FAILED Reason Code: **PASS**
- ✅ Deterministic Classification: **PASS**
- ✅ Escalation Threshold: **PASS**
- ✅ Audit Trace Structure: **PASS**
- ⏭️ Audit Tables: **SKIP** (due to import issue, test via Flask app instead)

## Test Audit Insertion via Flask App

Since the direct import has a Pydantic compatibility issue, test audit insertion through the Flask app:

### 1. Start Flask App

```bash
cd "IFI Essay tool"
python flask_app.py
```

### 2. Upload a Test File

1. Navigate to `http://localhost:5000`
2. Log in (or create account)
3. Upload a test PDF/image
4. Wait for processing to complete

### 3. Verify Audit Trail in Supabase

Run these SQL queries in your Supabase SQL editor:

```sql
-- Get the latest submission ID
SELECT submission_id, filename, created_at 
FROM submissions 
ORDER BY created_at DESC 
LIMIT 1;

-- Replace 'YOUR_SUBMISSION_ID' with the actual ID from above
-- Get the audit trace
SELECT 
    submission_id,
    trace_version,
    input->>'filename' as filename,
    signals->>'ocr' as ocr_signals,
    outcome->>'needs_review' as needs_review,
    outcome->>'review_reason_codes' as reason_codes,
    created_at
FROM submission_audit_traces 
WHERE submission_id = 'YOUR_SUBMISSION_ID'
ORDER BY created_at DESC 
LIMIT 1;

-- Get all events for this submission
SELECT 
    event_type,
    actor_role,
    event_payload,
    created_at
FROM submission_audit_events 
WHERE submission_id = 'YOUR_SUBMISSION_ID'
ORDER BY created_at;
```

### 4. Expected Events

You should see these events in order:
1. `INGESTED` - File uploaded
2. `OCR_COMPLETE` - OCR finished
3. `EXTRACTION_COMPLETE` - Fields extracted
4. `VALIDATION_COMPLETE` - Validation done
5. `SAVED` - Record saved to database

### 5. Test OCR_FAILED

To test OCR failure handling:

1. **Option A**: Temporarily break Google Vision credentials
   ```bash
   export GOOGLE_CLOUD_VISION_CREDENTIALS_JSON='{"invalid":"json"}'
   ```

2. **Option B**: Upload a corrupted/unreadable file

3. Check the record:
   ```sql
   SELECT 
       submission_id,
       review_reason_codes,
       status
   FROM submissions 
   WHERE review_reason_codes LIKE '%OCR_FAILED%'
   ORDER BY created_at DESC 
   LIMIT 5;
   ```

### 6. Test Approval Event

1. Approve a record via the UI (`/review` page)
2. Check for `APPROVED` event:
   ```sql
   SELECT 
       submission_id,
       event_type,
       actor_role,
       event_payload->>'reviewer_user_id' as reviewer,
       created_at
   FROM submission_audit_events 
   WHERE event_type = 'APPROVED'
   ORDER BY created_at DESC 
   LIMIT 1;
   ```

### 7. Test Duplicate Skip

1. Upload the same file twice
2. Check for `DUPLICATE_SKIPPED` event:
   ```sql
   SELECT 
       submission_id,
       event_type,
       event_payload,
       created_at
   FROM submission_audit_events 
   WHERE event_type = 'DUPLICATE_SKIPPED'
   ORDER BY created_at DESC 
   LIMIT 1;
   ```

## Verification Checklist

After testing, verify:

- [ ] `submission_audit_traces` table has entries
- [ ] `submission_audit_events` table has entries
- [ ] Trace includes: input, signals, rules_applied, outcome, errors
- [ ] Events include: INGESTED, OCR_COMPLETE, EXTRACTION_COMPLETE, VALIDATION_COMPLETE, SAVED
- [ ] `OCR_FAILED` appears when OCR errors occur
- [ ] `ESCALATED` appears when confidence < 0.3
- [ ] Approval creates `APPROVED` event
- [ ] Duplicate uploads create `DUPLICATE_SKIPPED` event

## Quick SQL Queries

```sql
-- Count traces by submission
SELECT submission_id, COUNT(*) as trace_count
FROM submission_audit_traces
GROUP BY submission_id
ORDER BY trace_count DESC;

-- Count events by type
SELECT event_type, COUNT(*) as count
FROM submission_audit_events
GROUP BY event_type
ORDER BY count DESC;

-- Recent traces with reason codes
SELECT 
    submission_id,
    outcome->>'review_reason_codes' as reason_codes,
    outcome->>'needs_review' as needs_review,
    created_at
FROM submission_audit_traces
ORDER BY created_at DESC
LIMIT 10;

-- Check for OCR_FAILED
SELECT COUNT(*) as ocr_failed_count
FROM submission_audit_traces
WHERE outcome->>'review_reason_codes' LIKE '%OCR_FAILED%';

-- Check for ESCALATED
SELECT COUNT(*) as escalated_count
FROM submission_audit_traces
WHERE outcome->>'review_reason_codes' LIKE '%ESCALATED%';
```

## Troubleshooting

### No Traces/Events Appearing

1. Check environment variables:
   ```bash
   echo $SUPABASE_URL
   echo $SUPABASE_SERVICE_ROLE_KEY
   ```

2. Verify migration was applied:
   ```sql
   SELECT table_name 
   FROM information_schema.tables 
   WHERE table_schema = 'public' 
   AND table_name LIKE '%audit%';
   ```

3. Check Flask logs for errors:
   ```bash
   # Look for "Warning: Failed to insert audit" messages
   ```

### Pydantic Import Error

If you see Pydantic import errors:
```bash
pip install 'pydantic>=2.0' 'supabase>=2.0'
```

Or test via Flask app (which handles imports correctly).
