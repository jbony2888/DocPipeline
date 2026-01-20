# Render Deployment - Quick Reference

## Required Environment Variables for Render

### Web Service (Flask App)

Add these in Render Dashboard → Your Web Service → Environment:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
REDIS_URL=redis://default:YOUR_PASSWORD@YOUR_REDIS_HOST:PORT/0
GOOGLE_CLOUD_VISION_CREDENTIALS_JSON={"type":"service_account",...}
GROQ_API_KEY=gsk_your-key-here
FLASK_SECRET_KEY=generate-random-32-char-hex
FLASK_PORT=$PORT
APP_URL=https://your-app-name.onrender.com
```

### Worker Service (Background Worker)

Add these in Render Dashboard → Your Worker Service → Environment:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
REDIS_URL=redis://default:YOUR_PASSWORD@YOUR_REDIS_HOST:PORT/0
GOOGLE_CLOUD_VISION_CREDENTIALS_JSON={"type":"service_account",...}
GROQ_API_KEY=gsk_your-key-here
FLASK_SECRET_KEY=same-as-web-service
APP_URL=https://your-app-name.onrender.com
WORKER_ID=worker-1
```

## Your Redis Cloud URL

**Get this from your Redis Cloud dashboard:**
1. Go to your Redis Cloud dashboard
2. Select your database
3. Copy the connection URL
4. Format: `redis://default:YOUR_PASSWORD@YOUR_REDIS_HOST:PORT/0`

**Set this value in `REDIS_URL` for both Web Service and Worker Service on Render.**

## Build & Start Commands

### Web Service

**Build Command:**
```bash
pip install -r requirements-flask.txt && mkdir -p artifacts outputs data templates static/css static/js
```

**Start Command:**
```bash
gunicorn -w 2 --timeout 120 -b 0.0.0.0:$PORT flask_app:app
```

### Worker Service

**Build Command:**
```bash
pip install -r requirements-flask.txt && mkdir -p artifacts outputs data templates static/css static/js
```

**Start Command:**
```bash
python worker_rq.py
```

## Quick Checklist

### Setup
- [ ] Redis Cloud database created and running
- [ ] Redis URL copied from Redis Cloud dashboard

### Web Service
- [ ] Service created on Render
- [ ] Build command set
- [ ] Start command set (gunicorn)
- [ ] All environment variables added
- [ ] `REDIS_URL` set with your Redis Cloud URL

### Worker Service
- [ ] Background Worker created on Render
- [ ] Build command set
- [ ] Start command set (python worker_rq.py)
- [ ] All environment variables added (same as Web Service + WORKER_ID)
- [ ] `REDIS_URL` set with your Redis Cloud URL

### Verification
- [ ] Both services deployed successfully
- [ ] Worker logs show "✅ Connected to Redis successfully"
- [ ] Worker logs show "*** Listening on submissions..."
- [ ] Test upload works
- [ ] Progress updates in real-time
- [ ] Jobs process successfully

