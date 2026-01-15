# Redis/RQ + Email Notification Implementation

## Overview

This application now uses **Redis/RQ** for background job processing and sends **email notifications** when jobs complete or fail.

## Architecture

```
User Uploads Files
       │
       ▼
Flask App (Non-blocking)
   - Saves files to storage
   - Enqueues jobs to Redis
   - Returns immediately with job_id
       │
       ▼
Redis Queue
   - Stores job queue
   - Job status tracking
       │
       ▼
RQ Worker
   - Pulls jobs from Redis
   - Processes submissions
   - Sends email notifications
   - Updates job status
```

## What Was Implemented

### 1. Redis/RQ Job Queue

**Files Created/Modified:**
- `jobs/redis_queue.py` - Redis/RQ queue implementation
- `jobs/queue.py` - Queue interface (now uses Redis)
- `worker_rq.py` - RQ worker for processing jobs
- `docker-compose.yml` - Added Redis service

**Features:**
- ✅ Non-blocking uploads (returns immediately)
- ✅ Background job processing via RQ
- ✅ Job status tracking in Redis
- ✅ Automatic job distribution across workers

### 2. Email Notifications

**Files Created:**
- `utils/email_notification.py` - Email sending system
- `utils/__init__.py` - Utils package init
- `templates/job_status.html` - Job status page

**Features:**
- ✅ Email sent on job completion (success)
- ✅ Email sent on job failure
- ✅ HTML and plain text email support
- ✅ Job link in emails
- ✅ Extracts user email from Supabase JWT token
- ✅ Falls back gracefully if email fails (doesn't break jobs)

### 3. Job Status Endpoints

**New Routes:**
- `GET /jobs/<job_id>` - User-facing job status page
- `GET /api/job_status/<job_id>` - API endpoint for job status

**Features:**
- ✅ Real-time job status display
- ✅ Auto-refreshing status page
- ✅ Job details (timestamps, filename, errors)
- ✅ Link to review page when complete

### 4. Configuration

**Files Created:**
- `.env.example` - Complete environment variables template
- `DEPLOYMENT_INSTRUCTIONS.md` - Deployment guide
- `EMAIL_SETUP.md` - Email configuration guide
- `REDIS_SETUP.md` - Redis setup guide

## How It Works

### Upload Flow

1. **User uploads files** via web UI
2. **Flask app:**
   - Validates files
   - Saves to Supabase Storage
   - Enqueues job to Redis (non-blocking)
   - Returns immediately with `job_id`
3. **Frontend:**
   - Shows processing modal
   - Polls `/api/batch_status` every 2 seconds
   - Updates progress bar
   - Redirects to review page when complete

### Processing Flow

1. **RQ Worker:**
   - Polls Redis queue every 2 seconds
   - Picks up queued jobs
   - Processes submission (OCR, extraction)
   - Updates job status in Redis

2. **On Success:**
   - Saves record to Supabase
   - Sets job status to `finished`
   - Sends success email to user
   - Email includes job link and details

3. **On Failure:**
   - Sets job status to `failed`
   - Stores error message
   - Sends failure email to user
   - Email includes error details

### Email Notification Flow

1. **Job completes/fails** in worker
2. **Extract user email** from Supabase JWT token
3. **Get job ID** from RQ context
4. **Generate job URL** using `APP_URL` environment variable
5. **Send email** via SMTP:
   - HTML email with styling
   - Plain text fallback
   - Includes job ID, filename, timestamp, status
   - Includes link to job details page
   - Includes error message if failed

## Environment Variables

### Required

```bash
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Redis
REDIS_URL=redis://localhost:6379/0  # Local
# Or: redis://default:password@redis-12345.upstash.io:6379/0  # Production

# Google Cloud Vision
GOOGLE_CLOUD_VISION_CREDENTIALS_JSON={...}
GROQ_API_KEY=your-groq-key

# Flask
FLASK_SECRET_KEY=generate-random-secret-key
APP_URL=http://localhost:5000  # Or https://your-app.onrender.com
```

### Optional (for Email)

```bash
# SMTP Configuration (required for email notifications)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
SMTP_USE_TLS=true
FROM_EMAIL=your-email@gmail.com
```

**Note:** If SMTP is not configured, jobs will still process but no emails will be sent.

## Local Development

### Start Services

```bash
# Start all services
docker-compose up -d

# Check services
docker-compose ps

# View logs
docker-compose logs -f worker
```

### Test Email

```python
from utils.email_notification import send_job_completion_email

send_job_completion_email(
    user_email="test@example.com",
    job_id="test-123",
    job_status="completed",
    filename="test.pdf",
    job_url="http://localhost:5000/jobs/test-123"
)
```

## Production Deployment (Render)

### Step 1: Setup Redis

Choose one (all have free tiers):
1. **Upstash** - https://upstash.com/ (Recommended)
2. **Render Redis Addon** - Dashboard → Addons → Redis
3. **Redis Cloud** - https://redis.com/try-free/

Get `REDIS_URL` and add to environment variables.

### Step 2: Deploy Services

**Web Service:**
- Build: `pip install -r requirements-flask.txt`
- Start: `gunicorn -w 2 -b 0.0.0.0:$PORT flask_app:app`
- Add all environment variables

**Worker Service:**
- Build: `pip install -r requirements-flask.txt`
- Start: `python worker_rq.py`
- Add all environment variables (same as Web Service)

### Step 3: Configure Email

**Gmail Setup:**
1. Enable 2-Factor Authentication
2. Generate App Password (Google Account → Security → App Passwords)
3. Use App Password as `SMTP_PASS` (NOT regular password)

**Set Environment Variables:**
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-16-char-app-password
SMTP_USE_TLS=true
FROM_EMAIL=your-email@gmail.com
APP_URL=https://your-app.onrender.com
```

## Testing

### Test Upload

1. Upload a file via UI
2. Check worker logs: `docker-compose logs worker`
3. Should see: "📥 Processing job {job_id}"
4. Check email inbox for notification

### Test Job Status

1. Upload a file
2. Get job_id from response or logs
3. Visit: `http://localhost:5000/jobs/{job_id}`
4. Should see job status page with auto-refresh

### Test Email

1. Complete a job (upload and wait for processing)
2. Check email inbox
3. Should receive notification with job details

## Files Changed/Created

### New Files
- `jobs/redis_queue.py` - Redis/RQ implementation
- `worker_rq.py` - RQ worker
- `utils/email_notification.py` - Email system
- `utils/__init__.py` - Utils package
- `templates/job_status.html` - Job status page
- `.env.example` - Environment variables template
- `DEPLOYMENT_INSTRUCTIONS.md` - Deployment guide
- `EMAIL_SETUP.md` - Email setup guide
- `REDIS_SETUP.md` - Redis setup guide

### Modified Files
- `jobs/queue.py` - Now uses Redis instead of PostgreSQL
- `jobs/process_submission.py` - Added email notifications
- `flask_app.py` - Added `/jobs/<job_id>` route, updated imports
- `docker-compose.yml` - Added Redis service
- `requirements-flask.txt` - Added `redis`, `rq`, `pyjwt`

### Deprecated (But Kept for Reference)
- `jobs/pg_queue.py` - PostgreSQL queue (not used anymore)
- `worker.py` - PostgreSQL polling worker (not used anymore)

## Benefits

✅ **Non-blocking uploads** - Fast response times  
✅ **Reliable processing** - Redis/RQ handles retries and failures  
✅ **Email notifications** - Users know when jobs complete  
✅ **Job tracking** - Users can check job status anytime  
✅ **Scalable** - Can run multiple workers easily  
✅ **Free tier available** - Upstash, Redis Cloud offer free tiers  

## Next Steps

1. **Deploy Redis** (Upstash, Render Addon, or Redis Cloud)
2. **Set `REDIS_URL`** in environment variables
3. **Configure email** (Gmail, SendGrid, etc.)
4. **Update worker command** to `python worker_rq.py`
5. **Test upload and email** notifications

## Troubleshooting

See:
- `DEPLOYMENT_INSTRUCTIONS.md` - Deployment troubleshooting
- `EMAIL_SETUP.md` - Email troubleshooting
- `REDIS_SETUP.md` - Redis troubleshooting

