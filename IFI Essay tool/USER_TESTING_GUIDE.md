# IFI Essay Gateway - User Testing Guide

## Welcome!

Thank you for testing the IFI Essay Gateway! This tool helps teachers organize essay entries so more time can be spent reading students' stories.

---

## Getting Started




### Step 1: Sign Up / Log In

1. Go to the application URL (you'll receive this from the team)
2. Enter your email address
3. Click "Send Magic Link"
4. Check your email and click the magic link
5. You'll be automatically logged in and taken to the dashboard

---

## Testing the Application

### Step 2: Upload Entry Forms

1. On the dashboard, you'll see an upload section
2. **Choose your upload mode:**
   - **Single Entry:** Upload one form at a time
   - **Multiple Entries:** Upload several forms at once (recommended)

3. Click "Choose entry form(s)" and select your PDF or image files
   - You can select multiple files at once
   - Supported formats: PDF, PNG, JPG, JPEG

4. **Review your selected files:**
   - You'll see a list of selected files
   - You can remove files by clicking "Remove" if needed

5. Click "Process Entries"
   - You'll see a progress bar showing processing status
   - Wait for all files to finish processing
   - You'll be automatically taken to the review page when done

---

### Step 3: Review and Fix Records

After uploading, you'll see records that need review (missing information).

#### Using Bulk Edit (New Feature!)

**This is the main feature we want you to test!**

1. **Select records:**
   - Check the boxes next to records you want to update
   - You can click "Select All" to select everything
   - Or "Deselect All" to clear your selection

2. **Enter information:**
   - In the blue "Bulk Edit Selected Records" panel, enter:
     - **School Name** (e.g., "Lincoln Elementary")
     - **Grade** (e.g., "5", "K", or "Kindergarten")
   - You can enter just one field, or both

3. **Apply the changes:**
   - Click "Apply to Selected (X)" where X is the number of selected records
   - Confirm in the popup window
   - Wait for the success message
   - The page will refresh showing your updates

#### Individual Record Actions

For each record, you can:
- **View PDF:** Click "View PDF (New Tab)" to see the original form
- **Edit:** Click "Edit" to fix individual record details
- **Approve:** Click "Approve" when a record is complete (has student name, school, and grade)
- **Delete:** Click "Delete" to remove a record (use carefully!)

---

### Step 4: View Organized Records

1. Click the "Approved Records" tab at the top
2. You'll see records organized by:
   - **School Name** → **Grade** → **Individual Records**
3. This makes it easy to find and export records by school or grade

---

### Step 5: Export Records

1. Go to the "Approved Records" view
2. You can export:
   - **All records:** Click "Export All to CSV" at the top
   - **By school:** Click "Export School" on a specific school card
   - **By grade:** Click "Export Grade" on a specific grade within a school
3. The CSV file will download with all the information, including links to the PDFs

---

## What to Test

### Please try these scenarios:

1. **Upload multiple files at once**
   - Select 5-10 files
   - See if they all process correctly

2. **Use bulk edit to fix school names**
   - Select 3-5 records missing school names
   - Enter a school name
   - Apply it to all selected records
   - Verify the school name appears on all selected records

3. **Use bulk edit to fix grades**
   - Select records missing grades
   - Try different grade formats:
     - Numbers: "5", "8", "12"
     - Text: "K", "Kindergarten", "Pre-K"
   - Verify grades are saved correctly

4. **Use bulk edit for both school and grade**
   - Select records missing both
   - Enter both school name and grade
   - Apply to all
   - Verify both fields are updated

5. **Test Select All / Deselect All**
   - Click "Select All" - all checkboxes should check
   - Click "Deselect All" - all checkboxes should uncheck

6. **Approve records**
   - After fixing records with bulk edit, approve them
   - They should move to the "Approved Records" view
   - They should be organized by school and grade

7. **Export records**
   - Export a CSV file
   - Open it and verify:
     - All information is correct
     - PDF links work
     - Records are properly formatted

---

## What to Report

If something doesn't work as expected, please note:

1. **What you were trying to do** (e.g., "Bulk edit school names")
2. **What happened** (e.g., "Got an error message")
3. **What you expected** (e.g., "Records should have updated")
4. **Screenshot** (if possible)

### Common Issues to Watch For:

- ❌ Bulk edit doesn't update records
- ❌ Error messages appear
- ❌ Records don't show updated information after bulk edit
- ❌ Can't select multiple records
- ❌ Export doesn't work
- ❌ PDFs don't open
- ❌ Page is slow or unresponsive

---

## Tips

- **Save your work:** Records are saved automatically, but you can refresh the page to see latest changes
- **Use bulk edit for efficiency:** If many records need the same school or grade, use bulk edit instead of editing one by one
- **Check before approving:** Make sure records have student name, school, and grade before approving
- **Export regularly:** Export your work as CSV files for backup

---

## Questions?

If you have questions or need help, contact the development team.

Thank you for testing! Your feedback helps make this tool better for all teachers.



