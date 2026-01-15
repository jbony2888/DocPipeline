# Background Processing Flow (Redis/RQ)

## Overview

The application now uses **Redis/RQ** for asynchronous background job processing. This means file uploads are processed in the background, allowing the web interface to remain responsive while files are being processed.

## Architecture

```
┌─────────────┐
│   Browser   │
│   (User)    │
└──────┬──────┘
       │
       │ 1. Upload files
       ▼
┌─────────────────────────────────┐
│      Flask App (Port 5000)      │
│                                 │
│  POST /upload                   │
│  ├─ Validates files             │
│  ├─ Reads file bytes            │
│  └─ Enqueues to Redis           │
│     └─ Returns job IDs          │
└──────┬──────────────────────────┘
       │
       │ 2. Enqueue job
       ▼
┌─────────────────────────────────┐
│      Redis Cloud                 │
│                                 │
│  Queue: "submissions"           │
│  ├─ Job 1: file1.pdf            │
│  ├─ Job 2: file2.pdf            │
│  └─ Job 3: file3.pdf            │
└──────┬──────────────────────────┘
       │
       │ 3. Worker picks up job
       ▼
┌─────────────────────────────────┐
│   RQ Worker (Background)         │
│                                 │
│  ├─ Downloads file from queue   │
│  ├─ Uploads to Supabase Storage │
│  ├─ Runs OCR (Google Vision)    │
│  ├─ Extracts data (Groq LLM)    │
│  ├─ Saves to database           │
│  └─ Sends email notification    │
└─────────────────────────────────┘
       │
       │ 4. Job complete
       ▼
┌─────────────────────────────────┐
│   Supabase Database             │
│                                 │
│  └─ New submission record       │
└─────────────────────────────────┘
```

## Step-by-Step Process

### 1. **User Uploads Files** (`POST /upload`)

When a user uploads files through the web interface:

```python
# flask_app.py - /upload route
for file in files:
    file_bytes = file.read()
    job_id = enqueue_submission(
        file_bytes=file_bytes,
        filename=file.filename,
        owner_user_id=user_id,
        access_token=access_token,
        ocr_provider="google"
    )
    job_ids.append({"filename": file.filename, "job_id": job_id})
```

**What happens:**
- Files are read into memory
- Each file is enqueued to Redis as a background job
- Job IDs are returned immediately (no waiting for processing)
- User sees "Processing..." status immediately

### 2. **Job Enqueued to Redis** (`jobs/redis_queue.py`)

```python
# redis_queue.py - enqueue_submission()
queue = get_queue()  # Connects to Redis Cloud
job = queue.enqueue(
    process_submission_job,  # Function to run
    file_bytes_base64,      # File data (base64 encoded)
    filename,
    owner_user_id,
    access_token,
    ocr_provider,
    job_timeout=3600  # 1 hour timeout
)
return job.id  # Returns immediately
```

**What happens:**
- File bytes are base64-encoded and stored in Redis
- Job is added to the "submissions" queue
- Returns job ID immediately (non-blocking)
- Flask app continues, doesn't wait for processing

### 3. **Worker Picks Up Job** (`worker_rq.py`)

The RQ worker runs continuously in the background:

```python
# worker_rq.py
worker = Worker([queue], connection=redis_client, name="worker-1")
worker.work()  # Continuously listens for jobs
```

**What happens:**
- Worker is always running (separate Docker container)
- Listens to Redis queue for new jobs
- When a job appears, worker picks it up automatically
- Processes job in background (doesn't block Flask app)

### 4. **Job Processing** (`jobs/process_submission.py`)

When worker picks up a job, it runs:

```python
# process_submission.py - process_submission_job()
def process_submission_job(file_bytes, filename, owner_user_id, ...):
    # 1. Upload to Supabase Storage
    ingest_data = ingest_upload_supabase(...)
    
    # 2. Run OCR (Google Vision)
    ocr_result = process_submission(tmp_path, ocr_provider="google")
    
    # 3. Extract data with LLM (Groq)
    # (if needed)
    
    # 4. Save to database
    save_db_record(record_dict, owner_user_id, access_token)
    
    # 5. Send email notification
    send_job_completion_email(...)
    
    return {"status": "success", "submission_id": ...}
```

**What happens:**
- File is uploaded to Supabase Storage
- OCR extracts text from image/PDF
- LLM extracts structured data (student name, school, grade)
- Record is saved to Supabase database
- Email notification sent to user
- Job status updated in Redis

### 5. **Status Polling** (Frontend)

The web interface polls for job status:

```javascript
// dashboard.html
function pollProgress() {
    fetch('/api/batch_status')
        .then(r => r.json())
        .then(data => {
            // Update progress bar
            // Show completed/failed counts
            // Redirect when all done
        });
}
```

**What happens:**
- Frontend polls `/api/batch_status` every few seconds
- Backend checks Redis for job status
- UI updates progress in real-time
- When all jobs complete, redirects to review page

## Key Benefits

### ✅ **Non-Blocking**
- User uploads files → gets immediate response
- No waiting for processing to complete
- Can upload multiple files simultaneously

### ✅ **Scalable**
- Multiple workers can process jobs in parallel
- Redis Cloud handles high load
- Jobs are distributed automatically

### ✅ **Reliable**
- Jobs persist in Redis (survive restarts)
- Failed jobs can be retried
- Email notifications on completion/failure

### ✅ **Real-Time Updates**
- Frontend polls for status
- Progress bars show completion
- Automatic redirect when done

## Monitoring

### Check Worker Status
```bash
docker-compose logs -f worker
```

### Check Redis Queue
```bash
docker-compose exec flask-app python -c "
from jobs.redis_queue import get_queue
q = get_queue()
print(f'Queue length: {len(q)}')
"
```

### Check Job Status
Visit: `http://localhost:5000/jobs/<job_id>`

## Email Notifications

When a job completes (success or failure), an email is automatically sent to the user with:
- Job status (completed/failed)
- Filename
- Job ID
- Link to view job details
- Error message (if failed)

## Configuration

### Environment Variables

- `REDIS_URL`: Redis Cloud connection string
  - Format: `redis://default:password@host:port/db`
  - Example: `redis://default:xxx@redis-xxx.cloud.redislabs.com:11474/0`

- `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON`: For OCR
- `GROQ_API_KEY`: For LLM extraction
- `SMTP_*`: For email notifications (optional)

## Troubleshooting

### Jobs Not Processing
1. Check worker is running: `docker-compose ps worker`
2. Check worker logs: `docker-compose logs worker`
3. Check Redis connection: `docker-compose exec flask-app python test_redis_connection.py`

### Jobs Stuck
1. Check Redis queue length
2. Restart worker: `docker-compose restart worker`
3. Check for errors in worker logs

### Slow Processing
1. Add more workers (scale horizontally)
2. Check Redis Cloud performance
3. Monitor Google Vision API quotas

