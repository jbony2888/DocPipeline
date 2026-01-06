# Flask Auth Callback Setup

## Problem
Streamlit can't handle URL hash fragments (`#access_token=...`) properly, so magic links don't work directly.

## Solution
Use a Flask callback service that handles the hash fragment and redirects to Streamlit.

## Quick Setup

### Step 1: Start Flask Service

Open a **NEW terminal window** and run:

```bash
cd "/Users/jerrybony/Documents/GitHub/DocPipeline/IFI Essay tool"
./START_FLASK_AUTH.sh
```

Or manually:
```bash
cd "/Users/jerrybony/Documents/GitHub/DocPipeline/IFI Essay tool"
export SUPABASE_URL="https://escbcdjlafzjxzqiephc.supabase.co"
export SUPABASE_ANON_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVzY2JjZGpsYWZ6anh6cWllcGhjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njc2NzgzNTcsImV4cCI6MjA4MzI1NDM1N30.kxxKhBcp1iZuwSrucZhBx31f59AlW3EO0pu279lIhJI"
export STREAMLIT_URL="http://localhost:8501"
export FLASK_SECRET_KEY="dev-secret-key-12345"
python auth_callback.py
```

You should see: `🚀 Flask auth callback service starting on http://0.0.0.0:5001`

**Keep this terminal open!** Flask needs to keep running.

### Step 2: Update Supabase Redirect URL

1. Go to: https://supabase.com/dashboard/project/escbcdjlafzjxzqiephc/auth/url-configuration
2. Under **Redirect URLs**, add: `http://localhost:5001/auth/callback`
3. Click **Save**

### Step 3: Restart Streamlit (if needed)

Make sure Streamlit is running:
```bash
docker-compose up -d essayflow
# or if running locally: streamlit run app.py
```

### Step 4: Test Magic Link

1. Go to `http://localhost:8501`
2. Enter your email and click "Send Login Link"
3. Check your email and click the magic link
4. **Flow:**
   - Magic link → Flask callback (`http://localhost:5001/auth/callback#access_token=...`)
   - Flask processes tokens → Redirects to Streamlit (`http://localhost:8501?auth_success=1`)
   - Streamlit reads Flask session → You're logged in! ✅

## How It Works

```
User clicks magic link
    ↓
Supabase redirects to Flask: http://localhost:5001/auth/callback#access_token=...
    ↓
Flask JavaScript extracts tokens from hash
    ↓
Flask sets Supabase session + stores in Flask session cookie
    ↓
Flask redirects to Streamlit: http://localhost:8501?auth_success=1&user_id=...
    ↓
Streamlit checks Flask session via API → User authenticated! ✅
```

## Troubleshooting

- **Flask not starting?** Check if port 5001 is available: `lsof -i :5001`
- **"Connection refused"** → Flask service isn't running, start it in a separate terminal
- **Still seeing login page?** → Check Flask logs for errors
- **Redirect loop?** → Make sure Supabase redirect URL is set correctly

## Production

For production, update:
- `STREAMLIT_URL` to your production domain
- `FLASK_AUTH_URL` to your production Flask service URL
- Add Flask service to docker-compose.yml or deploy separately

