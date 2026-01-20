# Testing Instructions for IFI Essay Gateway

## Overview
This document provides step-by-step testing instructions for the IFI Essay Gateway application, including the new bulk edit feature.

---

## Prerequisites

1. **Access to the application:**
   - Local: `http://localhost:5000`
   - Production: `https://docpipeline.onrender.com` (or your deployed URL)

2. **Test Account:**
   - You need a Supabase account with access to the application
   - Magic link login will be sent to your email

3. **Test Data:**
   - At least 5-10 submission records in "Needs Review" status
   - Some records should be missing school name or grade

---

## 1. Authentication Testing

### Test: Magic Link Login
1. Navigate to the login page: `/login`
2. Enter your email address
3. Click "Send Magic Link"
4. **Expected:** Success message appears
5. Check your email for the magic link
6. Click the magic link in the email
7. **Expected:** 
   - Redirected to dashboard
   - Your email appears in the top navigation bar
   - You can access all pages

### Test: Logout
1. Click "Logout" in the top navigation
2. **Expected:** 
   - Redirected to login page
   - Cannot access protected pages (redirected back to login)

### Test: Unauthenticated Access
1. While logged out, try to access:
   - `/upload` (should redirect to login)
   - `/review` (should redirect to login)
   - `/export_csv` (should redirect to login)
2. **Expected:** All redirect to login page

---

## 2. File Upload Testing

### Test: Single File Upload
1. Navigate to Dashboard (`/`)
2. Select "Single Entry" mode
3. Click "Choose entry form(s)" and select one PDF/image file
4. Click "Process Entries"
5. **Expected:**
   - Loading overlay appears
   - Progress bar shows processing status
   - Success notification appears when complete
   - Redirected to review page

### Test: Multiple File Upload
1. Navigate to Dashboard (`/`)
2. Select "Multiple Entries" mode (default)
3. Click "Choose entry form(s)" and select 3-5 files
4. **Expected:** Selected files appear in a list with remove buttons
5. Remove one file using the "Remove" button
6. **Expected:** File is removed from the list
7. Click "Process Entries"
8. **Expected:**
   - Loading overlay shows progress for all files
   - Estimated time remaining is displayed
   - All files process successfully
   - Redirected to review page after completion

### Test: File Selection Persistence
1. Select multiple files
2. Switch between "Single Entry" and "Multiple Entries" modes
3. **Expected:**
   - In "Single Entry" mode: Only first file is kept
   - In "Multiple Entries" mode: All files are kept

---

## 3. Bulk Edit Feature Testing

### Test: Basic Bulk Edit - School Name
1. Navigate to Review page: `/review?mode=needs_review`
2. **Verify:** Bulk Edit panel is visible (blue panel with "Bulk Edit Selected Records" header)
3. Select 2-3 records using checkboxes
4. **Expected:** Selected count updates (e.g., "Apply to Selected (2)")
5. Enter a school name in "School Name" field (e.g., "Lincoln Elementary")
6. Click "Apply to Selected"
7. **Expected:**
   - Confirmation modal appears
   - Click "Apply" in modal
   - Loading message appears
   - Success notification: "Successfully updated X records"
   - Page reloads after 1.5 seconds
   - Selected records now show the new school name

### Test: Basic Bulk Edit - Grade
1. Navigate to Review page: `/review?mode=needs_review`
2. Select 2-3 different records
3. Enter a grade in "Grade" field (e.g., "5" or "K")
4. Click "Apply to Selected"
5. **Expected:**
   - Confirmation modal appears
   - After confirmation, records are updated
   - Page reloads showing updated grades

### Test: Bulk Edit - Both School and Grade
1. Select 2-3 records
2. Enter both school name AND grade
3. Click "Apply to Selected"
4. **Expected:** Both fields are updated on all selected records

### Test: Select All / Deselect All
1. Click "Select All" button
2. **Expected:** All checkboxes are checked, count updates
3. Click "Deselect All" button
4. **Expected:** All checkboxes are unchecked, count shows 0

### Test: Grade Format Handling
Test with different grade formats:
- **Numeric:** "5" → Should save as `5`
- **Text:** "K" → Should save as `"K"`
- **Text:** "Kindergarten" → Should save as `"K"` (normalized)
- **Text:** "Pre-K" → Should save as `"Pre-K"`
- **Text:** "12th Grade" → Should extract `12` and save as `12`

### Test: Validation - No Selection
1. Don't select any records
2. Enter school name or grade
3. Click "Apply to Selected"
4. **Expected:** Error message: "Please select at least one record to update"

### Test: Validation - No Values
1. Select records
2. Leave both fields empty
3. Click "Apply to Selected"
4. **Expected:** Error message: "Please enter a School Name or Grade to apply"

### Test: Error Handling
1. Select records
2. Enter invalid data (if possible)
3. **Expected:** Appropriate error messages are shown

---

## 4. Review Page Testing

### Test: Needs Review View
1. Navigate to `/review?mode=needs_review`
2. **Expected:**
   - Shows records with missing required fields
   - Bulk edit panel is visible
   - Each record has a checkbox
   - Records are in an accordion (expandable/collapsible)

### Test: Approved Records View
1. Navigate to `/review?mode=approved`
2. **Expected:**
   - Records grouped by School → Grade
   - No bulk edit panel (only for needs_review)
   - Export buttons for each school/grade

### Test: Record Actions
1. Expand a record in "Needs Review"
2. **Expected:** Can see:
   - Student name, school, grade, teacher
   - Word count
   - Review reasons (if any)
   - "View PDF (New Tab)" button
   - "View Side-by-Side" button
   - "Edit", "Approve", "Delete" buttons

### Test: Approve Record
1. Click "Approve" on a record that has all required fields
2. **Expected:**
   - Confirmation modal appears
   - After confirmation, record moves to "Approved Records"
   - Success notification appears

### Test: Delete Record
1. Click "Delete" on a record
2. **Expected:**
   - Confirmation modal with warning
   - After confirmation, record is deleted
   - Success notification appears
   - Page reloads

---

## 5. Individual Record Edit Testing

### Test: Edit Record
1. Click "Edit" on a record
2. **Expected:** Navigate to record detail page
3. Modify school name or grade
4. Click "Save"
5. **Expected:**
   - Record is updated
   - Success message appears
   - If record now has all required fields, it may auto-approve

### Test: PDF Viewing
1. Click "View PDF (New Tab)" on a record
2. **Expected:** PDF opens in new tab
3. Click "View Side-by-Side"
4. **Expected:** PDF viewer appears below record details

---

## 6. Export Testing

### Test: Export All Records
1. Navigate to `/review?mode=approved`
2. Click "Export All to CSV"
3. **Expected:**
   - CSV file downloads
   - Contains all approved records
   - Includes PDF URL column

### Test: Export by School
1. Navigate to `/review?mode=approved`
2. Click "Export School" on a school card
3. **Expected:** CSV contains only records from that school

### Test: Export by Grade
1. Navigate to `/review?mode=approved`
2. Expand a school
3. Click "Export Grade" on a grade
4. **Expected:** CSV contains only records from that grade

---

## 7. Data Scoping Testing (Multi-User)

### Test: User Isolation
1. **As User A:**
   - Upload some files
   - Create some records
2. **As User B (different account):**
   - Log in
   - Navigate to review page
3. **Expected:** User B cannot see User A's records

### Test: Bulk Edit Scoping
1. **As User A:** Select and bulk edit some records
2. **As User B:** Try to access those record IDs
3. **Expected:** User B cannot see or edit User A's records

---

## 8. Error Scenarios

### Test: Network Error
1. Disconnect internet
2. Try to bulk edit
3. **Expected:** Appropriate error message

### Test: Invalid Data
1. Try to enter extremely long school names
2. Try invalid grade formats
3. **Expected:** Appropriate validation/error handling

### Test: Concurrent Edits
1. Open two browser tabs
2. Edit the same record in both
3. **Expected:** Last save wins (or appropriate conflict handling)

---

## 9. Performance Testing

### Test: Large Batch Upload
1. Upload 50+ files at once
2. **Expected:**
   - Progress tracking works
   - Time estimates are reasonable
   - All files process successfully

### Test: Bulk Edit Large Selection
1. Select 20+ records
2. Apply bulk edit
3. **Expected:**
   - All records update successfully
   - Reasonable response time (< 10 seconds)

---

## 10. UI/UX Testing

### Test: Responsive Design
1. Test on different screen sizes:
   - Desktop (1920x1080)
   - Tablet (768x1024)
   - Mobile (375x667)
2. **Expected:** Layout adapts appropriately

### Test: Loading States
1. Perform actions that trigger loading:
   - File upload
   - Bulk edit
   - Record approval
2. **Expected:** Clear loading indicators

### Test: Notifications
1. Perform various actions
2. **Expected:**
   - Success notifications appear
   - Error notifications appear
   - Notifications are dismissible
   - Notifications don't overlap

---

## Bug Reporting Template

When reporting bugs, please include:

```
**Bug Title:** [Brief description]

**Steps to Reproduce:**
1. 
2. 
3. 

**Expected Behavior:**
[What should happen]

**Actual Behavior:**
[What actually happens]

**Screenshots:**
[If applicable]

**Browser/OS:**
[E.g., Chrome 120 on macOS 14.2]

**Console Errors:**
[Open F12 → Console tab, copy any errors]

**Network Errors:**
[Open F12 → Network tab, check failed requests]
```

---

## Checklist for Complete Testing

- [ ] Authentication (login/logout)
- [ ] File upload (single and multiple)
- [ ] Bulk edit - school name
- [ ] Bulk edit - grade
- [ ] Bulk edit - both fields
- [ ] Select All / Deselect All
- [ ] Grade format handling (numeric and text)
- [ ] Validation (no selection, no values)
- [ ] Record approval
- [ ] Record deletion
- [ ] Individual record editing
- [ ] PDF viewing
- [ ] CSV export (all, by school, by grade)
- [ ] User data isolation
- [ ] Error handling
- [ ] Loading states
- [ ] Notifications

---

## Quick Test Scenarios

### Scenario 1: New Teacher Onboarding
1. Upload 10 files
2. Review records needing attention
3. Use bulk edit to set school name for 5 records
4. Use bulk edit to set grade for 3 records
5. Approve records that are now complete
6. Export approved records

### Scenario 2: Batch Correction
1. Select all records missing school name
2. Apply bulk edit with school name
3. Verify all records updated
4. Check that records moved to correct groups

### Scenario 3: Mixed Grade Handling
1. Upload forms with various grade formats (K, 5, Kindergarten, Pre-K)
2. Verify grades are stored correctly
3. Use bulk edit to standardize grades
4. Verify updates work correctly

---

## Notes

- **Data Persistence:** All changes are saved to Supabase PostgreSQL
- **File Storage:** Uploaded files are stored in Supabase Storage
- **Real-time Updates:** Page reloads after bulk edits to show latest data
- **Browser Compatibility:** Tested on Chrome, Firefox, Safari, Edge (latest versions)

---

## Contact

For questions or issues during testing, contact the development team.





