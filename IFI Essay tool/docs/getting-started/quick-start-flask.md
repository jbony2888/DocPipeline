# Quick Start: Flask Auth Service

## Step 1: Start Flask Service

**Open a NEW terminal window** and run:

```bash
cd "/Users/jerrybony/Documents/GitHub/DocPipeline/IFI Essay tool"
./START_FLASK_AUTH.sh
```

You should see:
```
🚀 Flask auth callback service starting on http://0.0.0.0:5001
📧 Magic links should redirect to: http://localhost:5001/auth/callback
 * Running on http://0.0.0.0:5001
```

**Keep this terminal open!** Flask must keep running.

## Step 2: Update Supabase Redirect URL

1. Go to: https://supabase.com/dashboard/project/escbcdjlafzjxzqiephc/auth/url-configuration
2. Under **Redirect URLs**, add: `http://localhost:5001/auth/callback`
3. Click **Save**

## Step 3: Test Magic Link

1. Go to `http://localhost:8501` (Streamlit app)
2. Enter your email → Click "Send Login Link"
3. Check email → Click the magic link
4. **Flow:**
   - Email link → Flask callback (`http://localhost:5001/auth/callback#access_token=...`)
   - Flask extracts tokens → Sets session → Redirects to Streamlit
   - Streamlit reads Flask session → **You're logged in!** ✅

## Troubleshooting

- **"Flask auth service not running"** → Start Flask in a separate terminal
- **"Connection refused"** → Flask isn't running on port 5001
- **Still on login page** → Check Flask terminal for errors
- **Redirect loop** → Verify Supabase redirect URL is `http://localhost:5001/auth/callback`

## How It Works

```
Magic Link Email
    ↓
Flask Callback Service (handles #access_token=...)
    ↓
Sets Supabase Session + Flask Session Cookie
    ↓
Redirects to Streamlit with ?auth_success=1
    ↓
Streamlit checks Flask session → Logged in! ✅
```





