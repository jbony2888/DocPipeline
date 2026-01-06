# 🔐 Authentication Debugging Guide

## Current Status

✅ **Flask service is running** on `http://localhost:5001`
✅ **Streamlit is running** on `http://localhost:8501`
✅ **Code fixes applied:**
- Fixed missing `os` import in `auth/auth_ui.py`
- Fixed duplicate code in `auth/auth_ui.py`
- Implemented token exchange mechanism

## How Magic Link Authentication Works

1. **User requests login link** → Streamlit sends email via Supabase
2. **User clicks email link** → Supabase redirects to Flask callback (`http://localhost:5001/auth/callback#access_token=...`)
3. **Flask extracts tokens** → JavaScript converts hash to query params, Flask processes tokens
4. **Flask creates exchange token** → Stores tokens temporarily, generates UUID token
5. **Flask redirects to Streamlit** → `http://localhost:8501?auth_token=<uuid>`
6. **Streamlit exchanges token** → Calls Flask `/auth/exchange` endpoint to get Supabase tokens
7. **Streamlit sets session** → Stores user info in `st.session_state`, user is logged in

## Required Setup Steps

### 1. Supabase Redirect URL Configuration

**CRITICAL:** You must configure Supabase to redirect to Flask, not Streamlit!

1. Go to: https://supabase.com/dashboard/project/escbcdjlafzjxzqiephc/auth/url-configuration
2. Under **Redirect URLs**, add:
   ```
   http://localhost:5001/auth/callback
   ```
3. Click **Save**

### 2. Start Flask Service

```bash
cd "/Users/jerrybony/Documents/GitHub/DocPipeline/IFI Essay tool"
./START_FLASK_AUTH.sh
```

**Keep this terminal open!** Flask must be running for authentication to work.

### 3. Verify Flask is Running

```bash
curl http://localhost:5001/
# Should return: {"status": "ok", "service": "Flask Auth Callback"}
```

Or run:
```bash
python test_auth_flow.py
```

## Testing the Flow

### Step-by-Step Test

1. **Open Streamlit**: http://localhost:8501
2. **Enter your email** in the login form
3. **Click "Send Login Link"**
4. **Check your email** for the magic link
5. **Click the magic link** in your email
6. **Expected flow:**
   - Browser opens Flask callback page (`http://localhost:5001/auth/callback#access_token=...`)
   - Flask page shows "Processing authentication..." briefly
   - Browser redirects to Streamlit (`http://localhost:8501?auth_token=...`)
   - Streamlit shows "✅ Login successful!" with balloons
   - You're now logged in!

## Common Issues & Solutions

### Issue: "Flask auth service not running!"

**Solution:**
```bash
./START_FLASK_AUTH.sh
```

### Issue: "Token expired or invalid"

**Causes:**
- Took too long to click the magic link (>60 seconds after Flask processed it)
- Token was already used (one-time use)

**Solution:** Request a new login link

### Issue: Redirect goes to wrong URL

**Check:**
1. Supabase redirect URL is set to: `http://localhost:5001/auth/callback`
2. Flask is running on port 5001
3. Streamlit is running on port 8501

### Issue: "No access token found" in Flask

**Causes:**
- Supabase redirect URL is wrong (should point to Flask, not Streamlit)
- Magic link expired
- JavaScript didn't execute (check browser console)

**Solution:**
1. Verify Supabase redirect URL configuration
2. Request a fresh magic link
3. Check browser console for JavaScript errors

### Issue: Streamlit can't connect to Flask

**Check:**
1. Flask is running: `ps aux | grep auth_callback`
2. Flask is accessible: `curl http://localhost:5001/`
3. No firewall blocking port 5001

## Debugging Commands

### Check Flask logs
```bash
# Flask logs are printed to terminal where you ran START_FLASK_AUTH.sh
# Look for lines starting with [Flask]
```

### Test Flask endpoints
```bash
# Health check
curl http://localhost:5001/

# Session check (should return {"authenticated": false} if not logged in)
curl http://localhost:5001/auth/session

# Test exchange endpoint (will fail without valid token, that's OK)
curl "http://localhost:5001/auth/exchange?token=test"
```

### Check Streamlit logs
```bash
docker-compose logs essayflow | tail -50
```

### Verify environment variables
```bash
# In Flask terminal, check:
echo $SUPABASE_URL
echo $STREAMLIT_URL
echo $FLASK_PORT

# In Streamlit (Docker), check:
docker-compose exec essayflow env | grep -E "SUPABASE|FLASK|STREAMLIT"
```

## Browser Console Debugging

Open browser DevTools (F12) and check:

1. **Console tab** - Look for:
   - `[Flask Callback]` messages
   - `[Login Page]` messages
   - Any JavaScript errors

2. **Network tab** - Check:
   - `/auth/callback` request (should be 200)
   - `/auth/exchange` request (should be 200 with tokens)
   - Any failed requests

## Expected Console Output

### Flask Terminal
```
🚀 Flask auth callback service starting on http://0.0.0.0:5001
📧 Magic links should redirect to: http://localhost:5001/auth/callback
[Flask] Setting session with access_token: eyJhbGciOiJIUzI1NiIs...
[Flask] User authenticated: user@example.com
[Flask] Redirecting to Streamlit with exchange token
```

### Browser Console (when clicking magic link)
```
[Flask Callback] Extracting tokens from URL hash...
[Flask Callback] Tokens found: {hasAccessToken: true, hasRefreshToken: true}
[Flask Callback] Redirecting to: /auth/callback?access_token=...
```

## Still Not Working?

1. **Check all services are running:**
   ```bash
   ps aux | grep -E "streamlit|flask|auth_callback"
   ```

2. **Verify Supabase redirect URL** (most common issue!)

3. **Request a fresh magic link** (old links expire)

4. **Check browser console** for JavaScript errors

5. **Check Flask terminal** for error messages

6. **Try incognito/private window** to rule out cookie issues

7. **Verify ports are not blocked:**
   ```bash
   lsof -i :5001  # Flask
   lsof -i :8501  # Streamlit
   ```

## Next Steps After Login Works

Once authentication is working:
1. Test with two different Supabase accounts
2. Verify data scoping (Teacher A can't see Teacher B's data)
3. Test logout functionality
4. Test session persistence (refresh page, should stay logged in)

