# Manual Test Checklist - Required Metadata Validation

This checklist verifies that required metadata validation is enforced and records cannot be approved without student_name, school_name, and grade.

## Prerequisites

1. Clear the database: `rm data/submissions.db` (or delete via UI)
2. Start the app: `streamlit run app.py`
3. Navigate to `http://localhost:8501`

## Test Cases

### Test 1: Upload Form with Missing Student Name

**Steps:**
1. Upload a test PDF/image (or use existing artifact)
2. Manually edit the record to remove/clear student_name field
3. Attempt to approve the record

**Expected Result:**
- ❌ Approval button should show error: "Cannot approve: Missing required fields: Student Name"
- Record remains in "Needs Review" status
- `needs_review=True` in database

**Verification:**
- [ ] Error message appears when attempting approval
- [ ] Record stays in "Needs Review" section
- [ ] Database shows `needs_review=1` (or True)

---

### Test 2: Upload Form with Missing School Name

**Steps:**
1. Upload a test PDF/image
2. Manually edit the record to remove/clear school_name field
3. Attempt to approve the record

**Expected Result:**
- ❌ Approval button should show error: "Cannot approve: Missing required fields: School Name"
- Record remains in "Needs Review" status

**Verification:**
- [ ] Error message appears
- [ ] Record stays in "Needs Review" section
- [ ] Database shows `needs_review=1`

---

### Test 3: Upload Form with Missing Grade

**Steps:**
1. Upload a test PDF/image
2. Manually edit the record to remove/clear grade field
3. Attempt to approve the record

**Expected Result:**
- ❌ Approval button should show error: "Cannot approve: Missing required fields: Grade"
- Record remains in "Needs Review" status

**Verification:**
- [ ] Error message appears
- [ ] Record stays in "Needs Review" section
- [ ] Database shows `needs_review=1`

---

### Test 4: Upload Form with Multiple Missing Fields

**Steps:**
1. Upload a test PDF/image
2. Manually edit the record to remove student_name, school_name, and grade
3. Attempt to approve the record

**Expected Result:**
- ❌ Approval button should show error listing all missing fields: "Cannot approve: Missing required fields: Student Name, School Name, Grade"
- Record remains in "Needs Review" status

**Verification:**
- [ ] Error message lists all missing fields
- [ ] Record stays in "Needs Review" section

---

### Test 5: Approve Record After Adding Missing Fields

**Steps:**
1. Upload a test PDF/image with missing grade
2. Attempt to approve (should fail)
3. Edit the record to add grade (e.g., "5")
4. Save changes
5. Attempt to approve again

**Expected Result:**
- ❌ First approval attempt fails with error
- ✅ After adding grade, approval succeeds
- Record moves to "Approved Records" section
- Database shows `needs_review=0` (or False)

**Verification:**
- [ ] First approval fails
- [ ] After editing, approval succeeds
- [ ] Record appears in "Approved Records"
- [ ] Database shows `needs_review=0`

---

### Test 6: Complete Record Approval

**Steps:**
1. Upload a test PDF/image with all fields present (student_name, school_name, grade)
2. Attempt to approve the record

**Expected Result:**
- ✅ Approval succeeds immediately
- Record moves to "Approved Records" section
- Success notification appears

**Verification:**
- [ ] Approval succeeds without errors
- [ ] Record appears in "Approved Records"
- [ ] Success notification displayed

---

### Test 7: Quick Approve Button (View Mode)

**Steps:**
1. Upload a test PDF/image with missing grade
2. Go to "Review & Approval Workflow" section
3. Find the record in "Needs Review" mode
4. Click "✅ Approve" button (quick approve, not edit mode)

**Expected Result:**
- ❌ Approval fails with error message
- Record stays in "Needs Review"

**Verification:**
- [ ] Error notification appears
- [ ] Record remains in "Needs Review"

---

### Test 8: Approve Button in Edit Mode

**Steps:**
1. Upload a test PDF/image with missing grade
2. Go to "Review & Approval Workflow" section
3. Click "✏️ Edit" on a record
4. Leave grade field empty
5. Click "✅ Approve" button in edit mode

**Expected Result:**
- ❌ Approval fails with error message
- Edit mode remains open
- Record stays in "Needs Review"

**Verification:**
- [ ] Error notification appears
- [ ] Edit form remains visible
- [ ] Record remains in "Needs Review"

---

### Test 9: Approve After Editing in Edit Mode

**Steps:**
1. Upload a test PDF/image with missing grade
2. Go to "Review & Approval Workflow" section
3. Click "✏️ Edit" on a record
4. Enter grade value (e.g., "5")
5. Click "💾 Save Changes"
6. Click "✅ Approve" button

**Expected Result:**
- ✅ After saving with grade, approval succeeds
- Record moves to "Approved Records"

**Verification:**
- [ ] Save succeeds
- [ ] Approval succeeds after save
- [ ] Record appears in "Approved Records"

---

### Test 10: Database Integrity Check

**Steps:**
1. Upload a test PDF/image with missing grade
2. Attempt to approve (should fail)
3. Check database directly: `sqlite3 data/submissions.db "SELECT submission_id, student_name, school_name, grade, needs_review FROM submissions WHERE submission_id='<id>';"`

**Expected Result:**
- Database shows `needs_review=1` (or True)
- Grade field is NULL or empty

**Verification:**
- [ ] Database query shows `needs_review=1`
- [ ] Grade is NULL or empty

---

## Edge Cases

### Test 11: Whitespace-Only Fields

**Steps:**
1. Upload a test PDF/image
2. Edit record to set student_name to "   " (whitespace only)
3. Attempt to approve

**Expected Result:**
- ❌ Approval fails: "Missing required fields: Student Name"

**Verification:**
- [ ] Whitespace-only fields are treated as missing
- [ ] Error message appears

---

### Test 12: Grade Edge Cases

**Steps:**
1. Test with grade = "K" (should be valid)
2. Test with grade = 0 (should fail)
3. Test with grade = 13 (should fail)
4. Test with grade = "5" (string, should be valid)

**Expected Result:**
- ✅ Grade "K" allows approval
- ❌ Grade 0 fails approval
- ❌ Grade 13 fails approval
- ✅ Grade "5" (string) allows approval

**Verification:**
- [ ] "K" is accepted
- [ ] 0 and 13 are rejected
- [ ] String "5" is accepted

---

## Summary Checklist

After completing all tests, verify:

- [ ] No record missing student_name can be approved
- [ ] No record missing school_name can be approved
- [ ] No record missing grade can be approved
- [ ] Error messages clearly identify which fields are missing
- [ ] After editing to add missing fields, records can be approved
- [ ] Database integrity is maintained (needs_review flag is correct)
- [ ] All three approval button locations enforce validation:
  - [ ] Single file approval button
  - [ ] Edit mode approval button
  - [ ] Quick approve button (view mode)

## Running Unit Tests

To run automated unit tests:

```bash
# Install pytest if not already installed
pip install pytest

# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_validate.py
pytest tests/test_approval_gating.py

# Run with verbose output
pytest tests/ -v
```

Expected output: All tests should pass ✅



