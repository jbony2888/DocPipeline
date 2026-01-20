# Render Deployment Guide - Redis/RQ Setup

## Overview

This guide covers deploying the IFI Essay Gateway application to Render with Redis/RQ background processing.

## Required Services

You need **3 services** on Render:
1. **Web Service** - Flask application (handles uploads, serves UI)
2. **Worker Service** - RQ worker (processes jobs in background)
3. **Redis** - Job queue (can use Redis Cloud, Upstash, or Render addon)

---

## Step 1: Setup Redis Cloud

### Option A: Redis Cloud (Recommended - Free Tier Available)

1. **Create Account:**
   - Go to https://redis.com/try-free/
   - Sign up for free account

2. **Create Database:**
   - Click "Create Database"
   - Choose free tier (30MB storage)
   - Select region closest to your Render region
   - Copy connection URL

3. **Connection URL Format:**
   ```
   redis://default:PASSWORD@HOST:PORT/0
   ```
   Example:
   ```
   redis://default:YOUR_PASSWORD@YOUR_REDIS_HOST:PORT/0
   ```

### Option B: Upstash Redis (Free Tier)

1. Go to https://upstash.com/
2. Create account and Redis database
3. Copy REST URL

### Option C: Render Redis Addon

1. Render Dashboard → Addons → Redis
2. Create Redis instance
3. `REDIS_URL` will be automatically set

---

## Step 2: Create Web Service (Flask App)

### Configuration

1. **Service Type:** Web Service
2. **Name:** `ifi-essay-gateway` (or your preferred name)
3. **Environment:** Python 3
4. **Region:** Oregon (or closest to your users)
5. **Branch:** `main` (or your deployment branch)

### Build & Start Commands

**Build Command:**
```bash
pip install -r requirements-flask.txt && mkdir -p artifacts outputs data templates static/css static/js
```

**Start Command:**
```bash
gunicorn -w 2 --timeout 120 -b 0.0.0.0:$PORT flask_app:app
```

### Environment Variables

Add these in Render Dashboard → Environment:

```
# Supabase Configuration (Required)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here

# Redis Configuration (Required)
REDIS_URL=redis://default:YOUR_PASSWORD@YOUR_REDIS_HOST:PORT/0

# Google Cloud Vision (Required)
GOOGLE_CLOUD_VISION_CREDENTIALS_JSON={"type":"service_account","project_id":"...","private_key":"...","client_email":"..."}

# Groq API Key (Required)
GROQ_API_KEY=gsk_your-groq-key-here

# Flask Configuration (Required)
FLASK_SECRET_KEY=generate-random-32-char-hex-string
FLASK_PORT=$PORT

# Application URL (Required for email links)
APP_URL=https://your-app-name.onrender.com

# Email Configuration (Optional but recommended)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
SMTP_USE_TLS=true
FROM_EMAIL=your-email@gmail.com
```

---

## Step 3: Create Worker Service (Background Worker)

### Configuration

1. **Service Type:** Background Worker
2. **Name:** `ifi-essay-gateway-worker` (or your preferred name)
3. **Environment:** Python 3
4. **Region:** Same as Web Service
5. **Branch:** `main` (or your deployment branch)

### Build & Start Commands

**Build Command:**
```bash
pip install -r requirements-flask.txt && mkdir -p artifacts outputs data templates static/css static/js
```

**Start Command:**
```bash
python worker_rq.py
```

### Environment Variables

**Copy ALL the same environment variables from Web Service**, plus:

```
# Worker Configuration (Required)
WORKER_ID=worker-1

# All other variables same as Web Service:
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here
REDIS_URL=redis://default:YOUR_PASSWORD@YOUR_REDIS_HOST:PORT/0
GOOGLE_CLOUD_VISION_CREDENTIALS_JSON={"type":"service_account",...}
GROQ_API_KEY=gsk_your-groq-key-here
FLASK_SECRET_KEY=same-as-web-service
APP_URL=https://your-app-name.onrender.com

# Email (same as Web Service)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
SMTP_USE_TLS=true
FROM_EMAIL=your-email@gmail.com
```

---

## Step 4: Generate Required Keys

### Generate FLASK_SECRET_KEY

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output and use it for `FLASK_SECRET_KEY` in both services.

### Get Your Redis Cloud URL

From Redis Cloud dashboard:
- Copy the connection URL
- Format: `redis://default:PASSWORD@HOST:PORT/0`

---

## Step 5: Verify Deployment

### Check Services

1. **Web Service:**
   - Should show "Running" status
   - Visit your app URL
   - Should see login page

2. **Worker Service:**
   - Should show "Running" status
   - Check logs: Should see "🚀 RQ Worker worker-1 started"
   - Should see "✅ Connected to Redis successfully"

### Test Upload

1. **Login** to your app
2. **Upload a test file**
3. **Check progress modal** - Should show real-time updates
4. **Check worker logs** - Should show job processing
5. **Wait for completion** - Should redirect to review page

---

## Environment Variables Checklist

### Web Service (Required):
- ✅ `SUPABASE_URL`
- ✅ `SUPABASE_ANON_KEY`
- ✅ `SUPABASE_SERVICE_ROLE_KEY`
- ✅ `REDIS_URL`
- ✅ `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON`
- ✅ `GROQ_API_KEY`
- ✅ `FLASK_SECRET_KEY`
- ✅ `FLASK_PORT` (set to `$PORT`)
- ✅ `APP_URL`

### Worker Service (Required):
- ✅ All Web Service variables PLUS:
- ✅ `WORKER_ID`

### Optional (Email Notifications):
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASS`
- `SMTP_USE_TLS`
- `FROM_EMAIL`

---

## Troubleshooting

### Worker Not Starting

**Check logs:**
```
Worker logs should show:
- "🚀 RQ Worker worker-1 started"
- "✅ Connected to Redis successfully"
- "*** Listening on submissions..."
```

**If not:**
1. Verify `REDIS_URL` is correct
2. Check Redis Cloud dashboard - database should be active
3. Verify password in `REDIS_URL`

### Jobs Not Processing

**Check:**
1. Worker is running (check status)
2. Redis connection working (check worker logs)
3. Web service can connect to Redis (check web logs)
4. Jobs are being enqueued (check web logs on upload)

### Progress Not Updating

**Check:**
1. Web service has `REDIS_URL` set
2. Job IDs are being stored in session
3. `/api/batch_status` endpoint is working
4. Frontend is polling correctly

---

## Quick Deploy Checklist

- [ ] Redis Cloud database created
- [ ] Redis connection URL copied
- [ ] Web Service created on Render
- [ ] Worker Service created on Render
- [ ] All environment variables set for Web Service
- [ ] All environment variables set for Worker Service
- [ ] `REDIS_URL` set in both services
- [ ] `FLASK_SECRET_KEY` generated and set
- [ ] `APP_URL` set to your Render URL
- [ ] Both services deployed successfully
- [ ] Test upload works
- [ ] Progress updates in real-time
- [ ] Jobs process in background
- [ ] Email notifications work (if configured)

---

## Get Your Redis Cloud URL

**From Redis Cloud Dashboard:**
1. Go to https://redis.com/ (or your Redis Cloud dashboard)
2. Select your database
3. Navigate to "Configuration" or "Connection Details"
4. Copy the connection URL
5. Format: `redis://default:YOUR_PASSWORD@YOUR_REDIS_HOST:PORT/0`

**⚠️ Never commit your Redis password to git!**

**Set this value in `REDIS_URL` for both Web Service and Worker Service on Render.**

---

## Support

If you encounter issues:
1. Check Render service logs
2. Verify all environment variables are set
3. Test Redis connection from worker logs
4. Check job status via `/api/batch_status` endpoint

