# Supabase Database Setup

This directory contains SQL scripts to set up the database tables in Supabase PostgreSQL.

## Quick Setup

### Option 1: Run Complete Setup Script (Recommended)

1. Go to your Supabase SQL Editor:
   - https://supabase.com/dashboard/project/YOUR_PROJECT_ID/sql/new
   - Replace `YOUR_PROJECT_ID` with your actual project ID (e.g., `escbcdjlafzjxzqiephc`)

2. Open `setup_database.sql` in this directory

3. Copy the entire contents and paste into the SQL Editor

4. Click **Run** to execute

This will create:
- ✅ `submissions` table with all required columns
- ✅ Indexes for performance
- ✅ Row Level Security (RLS) policies
- ✅ Auto-update trigger for `updated_at` timestamp
- ✅ Proper permissions

### Option 2: Run Migrations Individually

If you prefer to run migrations step by step:

1. Run `001_create_submissions_table.sql` first
2. Run `002_add_essay_text_column.sql` (optional)

## What Gets Created

### Tables

**`public.submissions`**
- Stores all essay submission records
- Each record is owned by a teacher (`owner_user_id`)
- Includes all metadata: student name, school, grade, etc.

### Security (RLS Policies)

Row Level Security ensures:
- ✅ Teachers can only see their own submissions
- ✅ Teachers can only create submissions for themselves
- ✅ Teachers can only update their own submissions
- ✅ Teachers can only delete their own submissions

### Indexes

Created for performance:
- `idx_submissions_owner_user_id` - Fast filtering by teacher
- `idx_submissions_needs_review` - Fast filtering by review status
- `idx_submissions_created_at` - Fast sorting by date
- `idx_submissions_grade` - Fast filtering by grade
- `idx_submissions_school_name` - Fast filtering by school

## Verification

After running the setup script, verify everything works:

```sql
-- Check table exists
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'submissions'
);

-- Check RLS is enabled
SELECT tablename, rowsecurity 
FROM pg_tables 
WHERE tablename = 'submissions';

-- Check policies exist
SELECT policyname, cmd 
FROM pg_policies 
WHERE tablename = 'submissions';

-- Check indexes
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'submissions';
```

## Schema Reference

### submissions table columns

| Column | Type | Description |
|--------|------|-------------|
| `submission_id` | TEXT | Primary key, unique identifier |
| `student_name` | TEXT | Student's name |
| `school_name` | TEXT | School name |
| `grade` | INTEGER | Grade level |
| `teacher_name` | TEXT | Teacher's name |
| `city_or_location` | TEXT | Location |
| `father_figure_name` | TEXT | Name of father/father-figure |
| `phone` | TEXT | Contact phone |
| `email` | TEXT | Contact email |
| `word_count` | INTEGER | Essay word count |
| `ocr_confidence_avg` | REAL | OCR confidence score |
| `needs_review` | BOOLEAN | Whether review is needed |
| `review_reason_codes` | TEXT | Semicolon-separated reason codes |
| `artifact_dir` | TEXT | Path to stored artifacts |
| `filename` | TEXT | Original filename |
| `essay_text` | TEXT | Full essay text (optional) |
| `owner_user_id` | UUID | Foreign key to auth.users(id) |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last update timestamp |

## Troubleshooting

### "relation already exists" error
- The table already exists. This is fine - the script uses `IF NOT EXISTS`
- If you need to recreate, drop the table first: `DROP TABLE public.submissions CASCADE;`

### "permission denied" error
- Make sure you're running as a database admin/superuser
- Check that you have the correct permissions in Supabase

### RLS policies not working
- Verify RLS is enabled: `ALTER TABLE public.submissions ENABLE ROW LEVEL SECURITY;`
- Check policies exist: `SELECT * FROM pg_policies WHERE tablename = 'submissions';`
- Ensure users are authenticated: policies use `auth.uid()` which requires authentication

## Next Steps

After setting up the database:

1. ✅ Configure Supabase Auth (already done via magic links)
2. ✅ Add redirect URLs in Supabase Dashboard
3. ✅ Test authentication flow
4. ✅ Verify RLS policies work correctly

## Notes

- **Current Implementation**: The app currently uses SQLite locally. These Supabase scripts are for migrating to PostgreSQL if desired.
- **Migration Path**: To migrate from SQLite to Supabase PostgreSQL, you would need to:
  1. Export data from SQLite
  2. Transform data format
  3. Import into Supabase PostgreSQL
  4. Update application code to use Supabase client instead of SQLite



