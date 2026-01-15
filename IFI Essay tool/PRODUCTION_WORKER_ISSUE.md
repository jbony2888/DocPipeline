# Production Issue: Jobs Stuck in Processing

## Issue Description
Client reports that file uploads show "Processing Submissions" with estimated time remaining, but jobs never complete (waited up to 15 minutes). The processing modal stays open indefinitely.

## Root Cause Analysis

The most likely causes are:

1. **Worker Not Running**: The background worker may not be running in production
2. **Worker Can't Access Jobs**: The worker might not have proper credentials to fetch/update jobs
3. **Worker Crashing Silently**: The worker might be crashing on job processing

## Immediate Diagnostic Steps

### 1. Check if Worker is Running
In production (Render), check if the worker service is running:
- Go to Render Dashboard
- Check if `worker` service is running (not crashed/stopped)
- Check worker logs for errors

### 2. Check Environment Variables
Verify these are set in production:
- `SUPABASE_SERVICE_ROLE_KEY` - **CRITICAL for worker**
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON`
- `GROQ_API_KEY`

### 3. Check Worker Logs
Look for:
- Worker startup messages: "🚀 Worker {WORKER_ID} started"
- Job processing messages: "📥 Processing job {job_id}"
- Error messages
- Any crashes or exceptions

### 4. Check Database
Query the jobs table to see job statuses:
```sql
SELECT id, status, created_at, started_at, finished_at, error_message 
FROM jobs 
ORDER BY created_at DESC 
LIMIT 10;
```

Expected statuses:
- `queued` - Waiting for worker
- `started` - Worker is processing
- `finished` - Completed successfully
- `failed` - Processing failed

## Quick Fixes

### Fix 1: Restart Worker Service
If worker is stopped/crashed:
1. Go to Render Dashboard
2. Find `worker` service
3. Click "Manual Deploy" or restart the service

### Fix 2: Verify Service Role Key
If `SUPABASE_SERVICE_ROLE_KEY` is missing or incorrect:
1. Get service role key from Supabase Dashboard
2. Add to Render environment variables
3. Restart worker service

### Fix 3: Check Worker Logs for Errors
Common errors:
- "SUPABASE_SERVICE_ROLE_KEY environment variable is required" - Missing key
- "Failed to create job in database" - RLS issue
- Google Cloud Vision errors - Missing/invalid credentials
- Any Python exceptions

## Diagnostic Endpoint (To Add)

Add this endpoint to help diagnose:

```python
@app.route("/api/worker_status")
def worker_status():
    """Diagnostic endpoint to check worker status."""
    # Check if jobs are being processed
    try:
        from supabase import create_client
        supabase_url = os.environ.get("SUPABASE_URL")
        service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        
        if not service_role_key:
            return jsonify({
                "worker_running": False,
                "error": "SUPABASE_SERVICE_ROLE_KEY not set"
            }), 500
        
        supabase = create_client(supabase_url, service_role_key)
        
        # Get recent jobs
        result = supabase.table("jobs").select("id, status, created_at, started_at, finished_at, error_message").order("created_at", desc=True).limit(10).execute()
        
        jobs = result.data if result.data else []
        
        # Count by status
        status_counts = {}
        for job in jobs:
            status = job.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Check if any jobs are stuck
        stuck_jobs = [j for j in jobs if j.get("status") == "queued" and j.get("created_at")]
        oldest_stuck = None
        if stuck_jobs:
            oldest_stuck = min(stuck_jobs, key=lambda x: x.get("created_at", ""))
        
        return jsonify({
            "worker_configured": True,
            "recent_jobs": len(jobs),
            "status_counts": status_counts,
            "oldest_stuck_job": {
                "id": oldest_stuck.get("id") if oldest_stuck else None,
                "created_at": oldest_stuck.get("created_at") if oldest_stuck else None
            } if oldest_stuck else None,
            "jobs": jobs[:5]  # Return first 5 for debugging
        })
    except Exception as e:
        return jsonify({
            "worker_running": False,
            "error": str(e)
        }), 500
```

## Expected Behavior

### When Working Correctly:
1. Files upload → Jobs created with status `queued`
2. Worker picks up jobs → Status changes to `started`
3. Worker processes → Progress updates
4. Job completes → Status changes to `finished` or `failed`
5. Frontend polling detects completion → Shows success, redirects to review page

### Current Issue:
- Jobs are created (`queued`)
- But worker never picks them up OR
- Worker picks them up but never completes them

## Verification Steps After Fix

1. Upload a single test file
2. Check `/api/worker_status` endpoint (if added)
3. Monitor job status in database
4. Check worker logs for processing messages
5. Verify job completes and frontend redirects

## Long-term Monitoring

Consider adding:
- Health check endpoint for worker
- Job timeout handling (if job is queued > 5 minutes, mark as failed)
- Worker heartbeat/status endpoint
- Automatic worker restart on failure

