# PostgreSQL Job Queue Setup

This application now uses **PostgreSQL (Supabase)** for the job queue instead of Redis. No external account setup is required!

## What Changed

- ✅ **Removed Redis** - No more Redis dependency
- ✅ **PostgreSQL Job Queue** - Uses your existing Supabase database
- ✅ **No External Accounts** - Everything runs through Supabase

## Setup Steps

### 1. Create the Jobs Table

Run the migration script in Supabase SQL Editor:

```sql
-- File: supabase/migrations/004_create_jobs_table.sql
```

Or run it directly:
1. Go to Supabase Dashboard > SQL Editor
2. Copy and paste the contents of `supabase/migrations/004_create_jobs_table.sql`
3. Click "Run"

### 2. Get Your Service Role Key

The worker needs the **service role key** to bypass Row Level Security (RLS) and process jobs:

1. Go to Supabase Dashboard > Settings > API
2. Find **"service_role"** key (NOT the anon key)
3. Copy it - you'll need it for the worker

⚠️ **Important**: The service role key has admin privileges. Keep it secret!

### 3. Set Environment Variables

Add to your `.env` file or Docker environment:

```bash
# Required for worker
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here

# Optional: Custom worker ID
WORKER_ID=worker-1
```

### 4. Update Docker Compose

The `docker-compose.yml` has been updated to:
- Remove Redis service
- Add `SUPABASE_SERVICE_ROLE_KEY` to worker environment
- Remove Redis dependencies

### 5. Restart Services

```bash
docker-compose down
docker-compose build
docker-compose up -d
```

## How It Works

1. **Job Creation**: When a user uploads files, jobs are created in the `jobs` table
2. **Worker Polling**: The worker polls the `jobs` table every 2 seconds for new jobs
3. **Job Processing**: Worker picks up jobs, processes them, and updates status
4. **Progress Tracking**: Frontend polls `/api/batch_status` to show progress

## Benefits

- ✅ **No External Services** - Uses existing Supabase database
- ✅ **No Account Setup** - Everything is already configured
- ✅ **Persistent** - Jobs survive server restarts
- ✅ **Scalable** - Can run multiple workers
- ✅ **Secure** - RLS policies ensure users only see their own jobs

## Troubleshooting

### Worker Not Processing Jobs

1. Check worker logs: `docker-compose logs worker`
2. Verify `SUPABASE_SERVICE_ROLE_KEY` is set correctly
3. Ensure jobs table exists: Check Supabase SQL Editor
4. Check RLS policies are correct

### Jobs Stuck in "queued" Status

1. Check worker is running: `docker-compose ps worker`
2. Check worker logs for errors
3. Verify service role key has correct permissions

### "Job not found" Errors

- Ensure RLS policies allow users to view their own jobs
- Check that `access_token` is being passed correctly

## Migration from Redis

If you were previously using Redis:

1. ✅ Jobs table migration is already included
2. ✅ Code has been updated to use PostgreSQL
3. ✅ Worker has been updated
4. ✅ Redis can be removed from your system

No data migration needed - new jobs will use PostgreSQL automatically!



