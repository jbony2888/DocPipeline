# Deployment Instructions - Redis/RQ with Email Notifications

## Overview

This application uses:
- **Flask** - Web application
- **Redis/RQ** - Job queue for background processing
- **SMTP** - Email notifications on job completion

## Local Development Setup

### 1. Start Services

```bash
# Start all services (Redis, Flask, Worker)
docker-compose up -d

# View logs
docker-compose logs -f

# Check services are running
docker-compose ps
```

### 2. Environment Variables

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
# Edit .env with your values
```

**Required:**
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `REDIS_URL` (defaults to `redis://redis:6379/0` in Docker)
- `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON`
- `GROQ_API_KEY`

**Email (Optional but recommended):**
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASS`
- `FROM_EMAIL`
- `APP_URL` (for job links in emails)

### 3. Test Locally

1. **Start services:**
   ```bash
   docker-compose up -d
   ```

2. **Check Redis:**
   ```bash
   docker-compose exec flask-app python -c "from jobs.redis_queue import get_redis_client; r = get_redis_client(); print('Redis:', r.ping())"
   ```

3. **Check worker:**
   ```bash
   docker-compose logs worker
   ```
   Should see: "🚀 RQ Worker {WORKER_ID} started"

4. **Upload a file** via the web UI

5. **Check email** - Should receive notification when job completes

## Production Deployment (Render)

### Step 1: Setup Redis

Choose one:

**Option A: Upstash Redis (Recommended - Free Tier)**
1. Go to https://upstash.com/
2. Create account and Redis database
3. Copy REST URL (format: `redis://default:password@redis-12345.upstash.io:6379/0`)

**Option B: Render Redis Addon**
1. Render Dashboard → Addons → Redis
2. Free tier available
3. `REDIS_URL` is set automatically

**Option C: Redis Cloud (Free Tier)**
1. Go to https://redis.com/try-free/
2. Create free database
3. Copy connection URL

### Step 2: Deploy Services on Render

#### Web Service (Flask App)

1. **Create Web Service:**
   - Connect your GitHub repo
   - Build Command: `pip install -r requirements-flask.txt`
   - Start Command: `gunicorn -w 2 -b 0.0.0.0:$PORT flask_app:app`
   - Environment: Python 3.11

2. **Environment Variables:**
   ```
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_ANON_KEY=your-anon-key
   SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
   REDIS_URL=redis://default:password@redis-12345.upstash.io:6379/0
   GOOGLE_CLOUD_VISION_CREDENTIALS_JSON={...}
   GROQ_API_KEY=your-groq-key
   FLASK_SECRET_KEY=generate-random-secret-key
   APP_URL=https://your-app.onrender.com
   
   # Email Configuration
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your-email@gmail.com
   SMTP_PASS=your-app-password
   SMTP_USE_TLS=true
   FROM_EMAIL=your-email@gmail.com
   ```

#### Worker Service

1. **Create Background Worker:**
   - Same repo as Web Service
   - Build Command: `pip install -r requirements-flask.txt`
   - Start Command: `python worker_rq.py`
   - Environment: Python 3.11

2. **Environment Variables:**
   ```
   # Same as Web Service, but add:
   WORKER_ID=worker-1
   
   # All other vars same as Web Service
   ```

### Step 3: Configure Email

#### Using Gmail SMTP

1. **Enable 2-Factor Authentication** on Gmail account

2. **Generate App Password:**
   - Google Account → Security → 2-Step Verification → App Passwords
   - Generate password for "Mail"
   - Use this as `SMTP_PASS`

3. **Set Environment Variables:**
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your-email@gmail.com
   SMTP_PASS=your-app-password  # App password, not regular password
   SMTP_USE_TLS=true
   FROM_EMAIL=your-email@gmail.com
   ```

#### Using Other SMTP Providers

- **SendGrid:** `smtp.sendgrid.net`, port 587
- **Mailgun:** `smtp.mailgun.org`, port 587
- **Amazon SES:** `email-smtp.region.amazonaws.com`, port 587

Update `SMTP_HOST` and `SMTP_PORT` accordingly.

### Step 4: Verify Deployment

1. **Check Web Service:**
   - Visit your app URL
   - Should load login page

2. **Check Worker:**
   - Render Dashboard → Worker Service → Logs
   - Should see: "🚀 RQ Worker {WORKER_ID} started"
   - Should see: "✅ Connected to Redis successfully"

3. **Test Upload:**
   - Upload a file
   - Check worker logs for processing
   - Check email inbox for notification

## Service Architecture

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │
       ▼
┌──────────────────┐
│   Flask Web      │ ← Handles uploads, enqueues jobs
│   Service        │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│   Redis Queue    │ ← Stores job queue
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│   RQ Worker      │ ← Processes jobs, sends emails
│   Service        │
└──────────────────┘
```

## Troubleshooting

### Jobs Not Processing

1. **Check Worker is Running:**
   - Render Dashboard → Worker Service → Should be "Active"

2. **Check Redis Connection:**
   - Worker logs should show: "✅ Connected to Redis successfully"
   - If not, check `REDIS_URL` is set correctly

3. **Check Worker Logs:**
   - Look for errors in worker logs
   - Should see job processing messages

### Emails Not Sending

1. **Check SMTP Configuration:**
   - Verify all SMTP_* variables are set
   - Check logs for SMTP errors

2. **Test SMTP Connection:**
   - Check worker logs for email send attempts
   - Look for "✅ Email notification sent" or errors

3. **Gmail App Password:**
   - Must use App Password, not regular password
   - Enable 2FA first

### Services Not Starting

1. **Check Environment Variables:**
   - All required vars must be set
   - No typos in variable names

2. **Check Build Logs:**
   - Ensure dependencies install correctly
   - Check for Python version issues

## Monitoring

### Check Job Status

- Visit: `https://your-app.onrender.com/api/worker_status`
- Shows recent jobs and their statuses

### Check Individual Job

- Visit: `https://your-app.onrender.com/jobs/{job_id}`
- Shows job details and progress

### View Logs

- Web Service: Render Dashboard → Web Service → Logs
- Worker Service: Render Dashboard → Worker Service → Logs

## Scaling

### Multiple Workers

To process jobs faster:

1. Create additional worker services
2. All use same `REDIS_URL`
3. RQ automatically distributes jobs across workers

### Worker Configuration

- **Single worker:** Handles 1 job at a time
- **Multiple workers:** Each handles 1 job, but can run in parallel
- **Concurrency:** RQ workers process sequentially (safe for database operations)

## Email Testing

Test email configuration locally:

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



