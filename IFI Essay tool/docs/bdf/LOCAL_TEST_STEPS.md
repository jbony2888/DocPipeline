# Local DBF Testing - Step by Step

## Step 1: Set Up Environment Variables

You need to set your Supabase credentials. Choose one method:

### Option A: Use .env file (Recommended)

```bash
cd "IFI Essay tool"

# Create .env file (if it doesn't exist)
./setup_local_test.sh

# Edit .env file with your credentials
# Then load it:
export $(cat .env | grep -v '^#' | xargs)
```

### Option B: Export directly

```bash
export SUPABASE_URL="https://your-project-id.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"
export SUPABASE_ANON_KEY="your-anon-key"
```

## Step 2: Run Core DBF Tests

```bash
cd "IFI Essay tool"
python test_dbf_local.py
```

**Expected output:**
```
✅ PASS: OCR_FAILED Reason Code
✅ PASS: Deterministic Classification
✅ PASS: Escalation Threshold
✅ PASS: Audit Trace Structure
```

## Step 3: Test Audit Insertion (via Flask App)

Since direct import may have issues, test through Flask:

```bash
# Start Flask app
python flask_app.py

# In another terminal, or use the web UI:
# 1. Navigate to http://localhost:5000
# 2. Log in
# 3. Upload a test file
```

## Step 4: Verify in Supabase

Run these queries in Supabase SQL Editor:

```sql
-- Check if tables exist
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name LIKE '%audit%';

-- Should return:
-- submission_audit_traces
-- submission_audit_events

-- Get latest trace
SELECT 
    submission_id,
    trace_version,
    input->>'filename' as filename,
    outcome->>'review_reason_codes' as reason_codes,
    created_at
FROM submission_audit_traces 
ORDER BY created_at DESC 
LIMIT 5;

-- Get latest events
SELECT 
    submission_id,
    event_type,
    actor_role,
    created_at
FROM submission_audit_events 
ORDER BY created_at DESC 
LIMIT 10;
```

## Step 5: Test Specific Scenarios

### Test OCR_FAILED

Upload a file that will cause OCR to fail (or temporarily break credentials), then:

```sql
SELECT 
    submission_id,
    review_reason_codes,
    status
FROM submissions 
WHERE review_reason_codes LIKE '%OCR_FAILED%'
ORDER BY created_at DESC 
LIMIT 1;
```

### Test Escalation

Upload a file with very low OCR confidence (< 0.3), then:

```sql
SELECT 
    submission_id,
    review_reason_codes
FROM submissions 
WHERE review_reason_codes LIKE '%ESCALATED%'
ORDER BY created_at DESC 
LIMIT 1;
```

### Test Approval Event

1. Approve a record via `/review` page
2. Check event:
```sql
SELECT 
    submission_id,
    event_type,
    actor_role,
    event_payload,
    created_at
FROM submission_audit_events 
WHERE event_type = 'APPROVED'
ORDER BY created_at DESC 
LIMIT 1;
```

## Quick Verification Commands

```bash
# Check environment is set
python -c "import os; print('SUPABASE_URL:', 'SET' if os.environ.get('SUPABASE_URL') else 'NOT SET')"

# Run all DBF tests
pytest tests/test_dbf_compliance.py tests/test_failure_injection.py -v

# Run local integration test
python test_dbf_local.py
```

## What to Look For

✅ **Success indicators:**
- Audit traces appear in `submission_audit_traces`
- Events appear in `submission_audit_events`
- `OCR_FAILED` reason code appears when OCR errors occur
- `ESCALATED` appears when confidence < 0.3
- `APPROVED` events appear when records are approved
- `DUPLICATE_SKIPPED` appears for duplicate uploads

❌ **Failure indicators:**
- No traces/events in database
- Import errors in Flask logs
- Missing reason codes
- Events not appearing

## Next Steps After Local Testing

Once local tests pass:
1. ✅ Verify migration applied correctly
2. ✅ Test audit insertion works
3. ✅ Deploy to staging/production
4. ✅ Monitor audit trail in production
5. ✅ Set up alerts for `ESCALATED` events
