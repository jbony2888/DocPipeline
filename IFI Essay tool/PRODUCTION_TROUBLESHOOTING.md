# Production Troubleshooting: Jobs Stuck in Processing

## Quick Check: Worker Status Endpoint

Visit this URL while logged in to check worker status:
```
https://your-app.onrender.com/api/worker_status
```

This will show:
- Whether worker is configured (has service role key)
- Recent job statuses
- If any jobs are stuck
- User's recent jobs

## Most Likely Issues

### 1. Worker Service Not Running (MOST LIKELY)
**Symptom**: Jobs stay in "queued" status forever, never get processed

**Check**: In Render Dashboard, verify the `worker` service is running (not stopped/crashed)

**Fix**: Restart the worker service in Render Dashboard

### 2. Missing Service Role Key
**Symptom**: Worker can't access jobs table

**Check**: Worker logs should show "SUPABASE_SERVICE_ROLE_KEY environment variable is required"

**Fix**: 
1. Get service role key from Supabase Dashboard (Settings > API > service_role key)
2. Add to Render environment variables for worker service
3. Restart worker service

### 3. Worker Crashes on Job Processing
**Symptom**: Jobs get picked up but fail immediately

**Check**: Worker logs for Python exceptions or errors

**Common causes**:
- Missing Google Cloud Vision credentials
- Missing GROQ_API_KEY
- Invalid file format
- Network issues accessing Supabase

## Diagnostic Steps

1. **Check Worker Service Status**
   - Go to Render Dashboard
   - Find `worker` service
   - Check if it's running (green) or stopped/crashed (red)

2. **Check Worker Logs**
   - Click on worker service
   - View logs
   - Look for:
     - "🚀 Worker {ID} started" (worker is running)
     - "📥 Processing job {id}" (jobs being picked up)
     - Error messages (worker is crashing)

3. **Check Environment Variables**
   - Verify these are set in Render for worker service:
     - `SUPABASE_SERVICE_ROLE_KEY` ✅ CRITICAL
     - `SUPABASE_URL`
     - `SUPABASE_ANON_KEY`
     - `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON`
     - `GROQ_API_KEY`

4. **Check Job Statuses in Database**
   - Use `/api/worker_status` endpoint
   - Or query Supabase directly:
   ```sql
   SELECT id, status, created_at, started_at, finished_at, error_message 
   FROM jobs 
   ORDER BY created_at DESC 
   LIMIT 10;
   ```

## Quick Fixes

### Fix 1: Restart Worker (Most Common Fix)
1. Render Dashboard → Worker Service
2. Click "Manual Deploy" or restart
3. Wait 30 seconds
4. Try uploading a file again

### Fix 2: Verify Service Role Key
1. Supabase Dashboard → Settings → API
2. Copy `service_role` key (NOT `anon` key)
3. Render Dashboard → Worker Service → Environment
4. Add/Update `SUPABASE_SERVICE_ROLE_KEY`
5. Restart worker service

### Fix 3: Check Worker Logs
If worker is crashing, logs will show the error:
- Missing credentials → Add missing env vars
- Python exceptions → Check error message
- Network errors → Check Supabase connection

## Expected Behavior When Working

1. **Upload files** → Jobs created (status: `queued`)
2. **Worker picks up** → Status changes to `started` (within 2-5 seconds)
3. **Processing** → Progress updates, OCR runs
4. **Complete** → Status changes to `finished` (within 30-60 seconds per file)
5. **Frontend detects** → Shows success, redirects to review page

## If Still Stuck

1. Check `/api/worker_status` endpoint output
2. Share worker logs
3. Share output from `/api/worker_status`
4. Check if any other services (flask-app, worker) are having issues

