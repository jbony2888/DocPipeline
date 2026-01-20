# Supabase Storage Setup Guide

## Error: Row Level Security Policy Violation

If you're getting this error:
```
❌ Error: Failed to upload file to Supabase Storage: {'statusCode': 403, 'error': Unauthorized, 'message': new row violates row-level security policy}
```

This means the storage bucket has Row Level Security (RLS) enabled but no policies allowing uploads.

## Solution: Create Storage Policies

### Step 1: Go to Supabase SQL Editor

1. Go to: https://supabase.com/dashboard/project/escbcdjlafzjxzqiephc/sql/new
2. Copy and paste the contents of `supabase/storage_policies.sql`
3. Click "Run" to execute

### Step 2: Verify Bucket Exists

1. Go to: https://supabase.com/dashboard/project/escbcdjlafzjxzqiephc/storage/buckets
2. Make sure `essay-submissions` bucket exists
3. If it doesn't exist, create it:
   - Click "New bucket"
   - Name: `essay-submissions`
   - Public: Choose based on your needs (see below)

### Step 3: Configure Bucket Settings

**Option A: Public Bucket (Recommended for shareable URLs in CSV exports)**
- Run the SQL script: `supabase/make_bucket_public.sql` in Supabase SQL Editor
- OR manually in Dashboard:
  - Go to Storage → Buckets → essay-submissions
  - Click "Settings" or "Edit"
  - Enable "Public bucket" toggle
- Files will be accessible via public URLs like:
  `https://escbcdjlafzjxzqiephc.supabase.co/storage/v1/object/public/essay-submissions/...`

**Option B: Private Bucket (More secure)**
- Keep bucket private
- Files accessible only to authenticated users
- Requires authenticated session token
- CSV export URLs will only work for logged-in users

### Step 4: Test Upload

After running the SQL policies, try uploading a file again. The policies allow:
- ✅ Authenticated users can upload to their own folder (`{user_id}/...`)
- ✅ Authenticated users can read files from their own folder
- ✅ Authenticated users can update/delete files in their own folder

## Policy Details

The policies ensure:
- Each user can only access files in their own folder
- File path structure: `{user_id}/{submission_id}/original.{ext}`
- Users cannot access other users' files

## Troubleshooting

### Still getting 403 errors?

1. **Check authentication**: Make sure you're logged in
2. **Check bucket name**: Must be exactly `essay-submissions`
3. **Check policies**: Run the SQL script again
4. **Check user ID**: The path must start with your user ID

### Check if policies exist:

```sql
SELECT * FROM pg_policies 
WHERE schemaname = 'storage' 
AND tablename = 'objects' 
AND policyname LIKE '%essay-submissions%';
```

### Manual policy creation:

If the SQL script doesn't work, create policies manually in Supabase Dashboard:
1. Go to Storage → Policies
2. Select `essay-submissions` bucket
3. Create policies for INSERT, SELECT, UPDATE, DELETE
4. Use the conditions from `storage_policies.sql`

