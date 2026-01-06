# Task 5: Batch Defaults Implementation

## Overview
Implemented batch defaults functionality for bulk uploads, allowing teachers to set default values (school_name, grade, teacher_name) that are applied to all submissions in a batch without overwriting manual edits.

## Database Changes

### Migration: `supabase/migrations/005_add_batch_defaults.sql`

1. **Created `upload_batches` table:**
   - `id` (UUID, primary key)
   - `owner_user_id` (UUID, references auth.users)
   - `created_at` (timestamptz)
   - `default_school_name` (TEXT, nullable)
   - `default_grade` (TEXT, nullable)
   - `default_teacher_name` (TEXT, nullable)

2. **Updated `submissions` table:**
   - Added `upload_batch_id` (UUID, FK to upload_batches)
   - Added `school_source` (TEXT, default 'extracted')
   - Added `grade_source` (TEXT, default 'extracted')
   - Added `teacher_source` (TEXT, default 'extracted')
   - Added check constraints for source values: 'extracted', 'batch_default', 'manual'

3. **RLS Policies:**
   - All tables have RLS enabled
   - Users can only access their own batches and submissions

## Code Changes

### 1. Service Functions (`pipeline/batch_defaults.py`)
- `create_upload_batch()` - Creates a new upload batch
- `get_batch_with_submissions()` - Gets batch with all submissions
- `apply_batch_defaults()` - Applies defaults to submissions (protects manual edits)

### 2. Upload Route (`flask_app.py`)
- Modified `/upload` route to create an upload batch before processing files
- Passes `upload_batch_id` to job processing

### 3. Job Processing
- Updated `jobs/pg_queue.py` to accept `upload_batch_id` parameter
- Updated `jobs/process_submission.py` to accept and pass `upload_batch_id`
- Updated `worker.py` to extract and pass `upload_batch_id` from job data

### 4. Database Functions (`pipeline/supabase_db.py`)
- Updated `save_record()` to accept `upload_batch_id` and set source tracking
- Sets default source values to 'extracted' for new records

### 5. Record Editing (`flask_app.py`)
- Updated `record_detail` route to set `source='manual'` when fields are edited
- Compares new values with existing values to detect changes

### 6. API Routes (`flask_app.py`)
- `GET /api/batches/<upload_batch_id>` - Get batch details
- `POST /api/batches/<upload_batch_id>/apply-defaults` - Apply defaults to batch

### 7. UI (`templates/review.html`)
- Added batch defaults panel (shown when batch_info is available)
- Form with inputs for default_school_name, default_grade, default_teacher_name
- JavaScript to handle form submission and show status

## How It Works

1. **Bulk Upload:**
   - User uploads multiple files
   - System creates an `upload_batch` record
   - Each file is processed and linked to the batch via `upload_batch_id`
   - Submissions are created with `source='extracted'` for all fields

2. **Setting Defaults:**
   - Teacher navigates to Review page (Needs Review mode)
   - If a batch is active (in session), batch defaults panel appears
   - Teacher enters default values and clicks "Apply Defaults"
   - System updates only empty/null fields where `source != 'manual'`
   - Sets `source='batch_default'` for updated fields

3. **Manual Edits:**
   - When teacher edits a field in record detail page
   - System detects the change and sets `source='manual'` for that field
   - Manual edits are protected from batch defaults

4. **Re-applying Defaults:**
   - Teacher can re-apply defaults multiple times
   - Only fields with `source != 'manual'` and empty/null values are updated
   - Manual edits are never overwritten

## Protection Logic

The `apply_batch_defaults()` function protects manual edits by:
1. Querying all submissions in the batch
2. For each submission, checking:
   - Field is empty/null AND
   - `source != 'manual'`
3. Only updating fields that meet both conditions
4. Setting `source='batch_default'` for updated fields

## Testing

### Manual Test Steps:

1. **Bulk Upload:**
   - Upload 5-10 files with mixed/missing school/grade data
   - Verify batch is created and submissions are linked

2. **Apply Defaults:**
   - Go to Review page (Needs Review mode)
   - Enter default school name and grade
   - Click "Apply Defaults"
   - Verify empty fields are filled

3. **Manual Override:**
   - Edit one submission's grade manually
   - Verify `grade_source` is set to 'manual'
   - Re-apply defaults
   - Verify the manually edited grade is NOT overwritten

4. **Re-apply Defaults:**
   - Apply defaults multiple times
   - Verify idempotent behavior (no duplicate updates)

### Unit Tests (To Be Created):

```python
def test_apply_defaults_protects_manual_edits():
    # Create batch with submissions
    # Mark one submission's grade_source='manual' with a value
    # Apply default_grade
    # Assert manual row unchanged, others updated

def test_apply_defaults_only_fills_empty_fields():
    # Create batch with mixed empty/non-empty fields
    # Apply defaults
    # Assert only empty fields are updated
```

## Files Changed

1. `supabase/migrations/005_add_batch_defaults.sql` - Database schema
2. `pipeline/batch_defaults.py` - Service functions (NEW)
3. `flask_app.py` - Routes and batch integration
4. `jobs/pg_queue.py` - Job queue with batch support
5. `jobs/process_submission.py` - Job processing with batch support
6. `worker.py` - Worker with batch support
7. `pipeline/supabase_db.py` - Save record with batch support
8. `templates/review.html` - UI for batch defaults

## Next Steps

1. Run SQL migration in Supabase Dashboard
2. Test bulk upload flow
3. Test batch defaults application
4. Test manual edit protection
5. Create unit tests for `apply_batch_defaults()` function

