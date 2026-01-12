# Debugging Flask Auth Service

## Check if Flask is Running

```bash
curl http://localhost:5001/
# Should return: {"status": "ok", "service": "Flask Auth Callback"}
```

## Test Flask Session Endpoint

```bash
curl http://localhost:5001/auth/session
# Should return: {"authenticated": false}
```

## Check Flask Logs

When Flask is running, you should see logs like:
- `[Flask] Setting session with access_token: ...`
- `[Flask] User authenticated: user@example.com`
- `[Flask] Redirecting to Streamlit: ...`

## Common Issues

### 1. Flask Not Running
**Symptom**: Streamlit shows "Flask auth service not running"
**Fix**: Start Flask in a separate terminal:
```bash
./START_FLASK_AUTH.sh
```

### 2. Supabase Redirect URL Wrong
**Symptom**: Magic link doesn't go to Flask
**Fix**: Update Supabase redirect URL to: `http://localhost:5001/auth/callback`

### 3. Session Not Persisting
**Symptom**: Flask authenticates but Streamlit doesn't see it
**Fix**: Check browser cookies - Flask session cookie should be set

### 4. CORS Issues
**Symptom**: Streamlit can't call Flask API
**Fix**: Both should be on localhost (they are)

## Manual Test Flow

1. **Start Flask**: `./START_FLASK_AUTH.sh`
2. **Verify Flask**: `curl http://localhost:5001/`
3. **Request magic link** from Streamlit
4. **Click magic link** - should go to Flask callback
5. **Check Flask terminal** for authentication logs
6. **Check Streamlit** - should redirect and log you in

## What to Check

1. ✅ Flask is running on port 5001
2. ✅ Supabase redirect URL is `http://localhost:5001/auth/callback`
3. ✅ Flask terminal shows authentication logs
4. ✅ Browser console shows no errors
5. ✅ Flask session cookie is set in browser



