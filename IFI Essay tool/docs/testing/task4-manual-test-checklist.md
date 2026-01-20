# Task 4 Manual Test Checklist - Teacher Login with Supabase Auth

This checklist verifies that authentication and user scoping work correctly.

## Prerequisites

1. **Supabase Setup:**
   - Create Supabase project at https://supabase.com
   - Get your project URL and anon key
   - Set environment variables:
     ```bash
     export SUPABASE_URL="https://your-project.supabase.co"
     export SUPABASE_ANON_KEY="your-anon-key"
     ```

2. **Create Test Accounts:**
   - Create Teacher A account: `teacherA@example.com`
   - Create Teacher B account: `teacherB@example.com`
   - Note passwords for both accounts

3. **Start the app:**
   ```bash
   streamlit run app.py
   ```

## Test Cases

### Test 1: Unauthenticated Access Blocked

**Steps:**
1. Open app in browser (or clear session state)
2. Try to access the app

**Expected Result:**
- ❌ Login screen is displayed
- ❌ Cannot see upload form
- ❌ Cannot see review workflow
- ❌ Cannot see any data

**Verification:**
- [ ] Login form appears
- [ ] No access to main app sections
- [ ] URL shows login page

---

### Test 2: Login with Email + Password

**Steps:**
1. Enter Teacher A email: `teacherA@example.com`
2. Enter password
3. Click "🔑 Sign In"

**Expected Result:**
- ✅ Login succeeds
- ✅ Redirected to main app
- ✅ Sidebar shows "Logged in as: teacherA@example.com"
- ✅ Can see upload form and review workflow

**Verification:**
- [ ] Login succeeds
- [ ] Main app loads
- [ ] User email visible in sidebar
- [ ] Can access all sections

---

### Test 3: Teacher A Cannot See Teacher B Records

**Steps:**
1. Log in as Teacher A
2. Upload a test file and process it
3. Note the submission_id
4. Logout
5. Log in as Teacher B
6. Go to "Review & Approval Workflow"

**Expected Result:**
- ✅ Teacher B sees empty list (or their own records only)
- ❌ Teacher B cannot see Teacher A's record
- ✅ Database query filters by owner_user_id

**Verification:**
- [ ] Teacher B's review list does not show Teacher A's record
- [ ] Database stats show 0 records for Teacher B
- [ ] Teacher A's record is not accessible

---

### Test 4: New Uploads Tagged with Owner

**Steps:**
1. Log in as Teacher A
2. Upload a test file
3. Process the file
4. Check database directly (or via app)

**Expected Result:**
- ✅ Record saved with `owner_user_id = Teacher A's user ID`
- ✅ Record appears in Teacher A's review list
- ✅ Record does not appear for other teachers

**Verification:**
- [ ] Record has correct owner_user_id
- [ ] Record visible to Teacher A
- [ ] Record not visible to Teacher B

---

### Test 5: Update Record Enforces Ownership

**Steps:**
1. Log in as Teacher A
2. Upload and process a file (get submission_id)
3. Logout
4. Log in as Teacher B
5. Try to edit Teacher A's record (if you know submission_id)

**Expected Result:**
- ❌ Teacher B cannot update Teacher A's record
- ✅ Update operation fails silently or returns error
- ✅ Record unchanged

**Verification:**
- [ ] Update fails (record not found or permission denied)
- [ ] Teacher A's record unchanged
- [ ] Teacher B cannot modify Teacher A's data

---

### Test 6: Delete Record Enforces Ownership

**Steps:**
1. Log in as Teacher A
2. Upload and process a file (get submission_id)
3. Logout
4. Log in as Teacher B
5. Try to delete Teacher A's record

**Expected Result:**
- ❌ Teacher B cannot delete Teacher A's record
- ✅ Delete operation fails
- ✅ Record still exists

**Verification:**
- [ ] Delete fails (record not found)
- [ ] Teacher A's record still exists
- [ ] Teacher B cannot delete Teacher A's data

---

### Test 7: Logout Blocks Access

**Steps:**
1. Log in as Teacher A
2. Upload and process a file
3. Click "🚪 Logout" in sidebar
4. Try to access app sections

**Expected Result:**
- ✅ Logout succeeds
- ✅ Session cleared
- ✅ Redirected to login screen
- ❌ Cannot access data after logout

**Verification:**
- [ ] Logout button works
- [ ] Login screen appears
- [ ] Cannot access upload/review sections
- [ ] Must log in again to access

---

### Test 8: Stats Filtered by Owner

**Steps:**
1. Log in as Teacher A
2. Upload 2 files, approve 1
3. Check database stats
4. Logout
5. Log in as Teacher B
6. Check database stats

**Expected Result:**
- ✅ Teacher A stats show: Total: 2, Clean: 1, Needs Review: 1
- ✅ Teacher B stats show: Total: 0, Clean: 0, Needs Review: 0
- ✅ Stats are scoped to logged-in user

**Verification:**
- [ ] Teacher A sees correct counts
- [ ] Teacher B sees 0 counts
- [ ] Stats match actual records for each user

---

### Test 9: Magic Link Authentication

**Steps:**
1. Logout if logged in
2. Enter Teacher A email
3. Click "📧 Send Magic Link"
4. Check email
5. Click magic link

**Expected Result:**
- ✅ Magic link email sent
- ✅ Clicking link signs in user
- ✅ User redirected to app

**Verification:**
- [ ] Email received
- [ ] Magic link works
- [ ] User logged in after clicking link

---

### Test 10: Multiple Teachers Can Use App Simultaneously

**Steps:**
1. Open app in Browser 1, log in as Teacher A
2. Open app in Browser 2 (incognito), log in as Teacher B
3. Upload files from both browsers
4. Check records in each browser

**Expected Result:**
- ✅ Both teachers can use app simultaneously
- ✅ Each teacher sees only their own records
- ✅ No data leakage between users

**Verification:**
- [ ] Both sessions work independently
- [ ] Teacher A sees only Teacher A records
- [ ] Teacher B sees only Teacher B records
- [ ] No cross-contamination

---

### Test 11: Database Migration

**Steps:**
1. Check if database exists
2. Start app (migration runs automatically)
3. Check database schema

**Expected Result:**
- ✅ Migration runs automatically on startup
- ✅ `owner_user_id` column added to submissions table
- ✅ Index created on `owner_user_id`

**Verification:**
- [ ] Migration completes without errors
- [ ] Column exists in database
- [ ] Index exists

---

### Test 12: Invalid Credentials

**Steps:**
1. Try to log in with wrong password
2. Try to log in with non-existent email

**Expected Result:**
- ❌ Login fails with error message
- ✅ Error message is user-friendly
- ✅ User can try again

**Verification:**
- [ ] Error message displayed
- [ ] Can retry login
- [ ] No app crash

---

## Summary Checklist

After completing all tests, verify:

- [ ] Unauthenticated users cannot access app
- [ ] Login works with email + password
- [ ] Login works with magic link
- [ ] Teachers cannot see other teachers' records
- [ ] New uploads tagged with owner_user_id
- [ ] Update operations enforce ownership
- [ ] Delete operations enforce ownership
- [ ] Stats filtered by owner
- [ ] Logout blocks access
- [ ] Multiple users can use app simultaneously
- [ ] Database migration works
- [ ] Error handling works correctly

## Database Verification

To verify user scoping directly in database:

```bash
# Connect to database
sqlite3 data/submissions.db

# Check owner_user_id column exists
.schema submissions

# Check records for Teacher A (replace with actual user_id)
SELECT submission_id, student_name, owner_user_id FROM submissions WHERE owner_user_id = 'teacher-a-user-id';

# Check records for Teacher B
SELECT submission_id, student_name, owner_user_id FROM submissions WHERE owner_user_id = 'teacher-b-user-id';

# Verify no cross-contamination
SELECT COUNT(*) FROM submissions WHERE owner_user_id IS NULL;
```

## Troubleshooting

**Login fails:**
- Check SUPABASE_URL and SUPABASE_ANON_KEY are set correctly
- Verify email exists in Supabase Auth
- Check Supabase project is active

**Records not showing:**
- Verify owner_user_id is set correctly
- Check database migration ran successfully
- Verify user_id matches in session state

**Migration errors:**
- Check database file permissions
- Verify SQLite version supports ALTER TABLE
- Check for existing column conflicts





