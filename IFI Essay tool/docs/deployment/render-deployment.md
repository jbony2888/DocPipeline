# Render Deployment Guide

## Required Environment Variables

Add these environment variables in your Render service settings:

### Supabase Configuration (Required)
```
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_ANON_KEY=your-supabase-anon-key-here
SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key-here
```

**Where to find these:**
- Go to Supabase Dashboard → Settings → API
- `SUPABASE_URL`: Your project URL
- `SUPABASE_ANON_KEY`: The "anon" public key
- `SUPABASE_SERVICE_ROLE_KEY`: The "service_role" secret key (⚠️ Keep this secret!)

### Flask Configuration (Required)
```
FLASK_SECRET_KEY=<generate-a-secure-random-key>
FLASK_PORT=10000
```

**Note:** 
- `FLASK_SECRET_KEY`: Generate a secure random key (e.g., `python -c "import secrets; print(secrets.token_hex(32))"`)
- `FLASK_PORT`: Render usually sets this automatically, but you can use `10000` as default

### API Keys (Required)
```
GROQ_API_KEY=<your-groq-api-key>
```

### Google Cloud Vision (Optional - if using Google OCR)
```
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json
```

**Note:** For Google Cloud credentials on Render:
- You'll need to upload the JSON credentials file
- Or set the entire JSON content as an environment variable and write it to a file at startup

### Worker Configuration (If running background worker)
```
WORKER_ID=worker-1
```

## Steps to Deploy on Render

### 1. Create Web Service
1. Go to Render Dashboard: https://dashboard.render.com
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Select the repository and branch

### 2. Configure Build Settings
- **Name**: `ifi-essay-gateway` (or your preferred name)
- **Environment**: `Python 3`
- **Build Command**: `pip install -r requirements-flask.txt`
- **Start Command**: `python flask_app.py`

### 3. Add Environment Variables
Go to "Environment" tab and add all the variables listed above.

### 4. Update Supabase Redirect URL (CRITICAL - DO THIS AFTER DEPLOYMENT)
After your app is deployed on Render, you **MUST** add your production URL to Supabase:

**Your Production URL:** `https://docpipeline.onrender.com`

1. Go to Supabase Dashboard: https://supabase.com/dashboard/project/escbcdjlafzjxzqiephc/auth/url-configuration
2. Under "Redirect URLs", add:
   ```
   https://docpipeline.onrender.com/auth/callback
   ```
3. Under "Site URL", set:
   ```
   https://docpipeline.onrender.com
   ```
4. Click "Save" to apply changes

**Important:** 
- Without this, magic link authentication will fail in production!
- The Flask app automatically detects the production URL from the request, but Supabase must allow it
- You can add both localhost (for development) and production URLs to the redirect list

### 5. (Optional) Create Background Worker Service
If you need background processing:
1. Create a new "Background Worker" service
2. Use the same repository
3. **Start Command**: `python worker.py`
4. Add the same environment variables (including `SUPABASE_SERVICE_ROLE_KEY`)

## Important Notes

### Security
- **Never commit** `FLASK_SECRET_KEY` or API keys to Git
- Use Render's environment variables for all secrets
- `SUPABASE_SERVICE_ROLE_KEY` should only be used by the worker service

### Port Configuration
- Render automatically sets `PORT` environment variable
- Update `flask_app.py` to use `os.environ.get("PORT", 5000)` if needed

### Google Cloud Credentials
If using Google Cloud Vision, you have two options:

**Option A: Upload credentials file**
- Upload `credentials.json` to Render
- Set `GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json`

**Option B: Use environment variable**
- Set entire JSON content as `GOOGLE_CREDENTIALS_JSON` environment variable
- Modify startup to write it to a file

## Verification Checklist

After deployment, verify:
- [ ] App starts without errors
- [ ] Login page loads
- [ ] Magic link authentication works
- [ ] File upload works
- [ ] PDF viewing works
- [ ] CSV export works
- [ ] Background worker processes jobs (if deployed)

## Troubleshooting

### App won't start
- Check environment variables are set correctly
- Check build logs for missing dependencies
- Verify Python version (3.11 recommended)

### Authentication not working
- Verify Supabase redirect URL is set correctly
- Check `SUPABASE_URL` and `SUPABASE_ANON_KEY` are correct

### Storage errors
- Verify bucket `essay-submissions` exists in Supabase
- Check storage policies are set up (run `supabase/storage_policies.sql`)
- Verify bucket is public if using shareable URLs

### Email Templates
To update the email templates in Supabase:

**1. Magic Link Template (for login):**
1. Go to Supabase Dashboard → Authentication → Email Templates
2. Select "Magic Link" template
3. Update the HTML with the template from `supabase/email_templates/magic_link.html`
4. The `{{ .ConfirmationURL }}` variable will be automatically replaced with the magic link

**2. Confirm Signup Template:**
1. Go to Supabase Dashboard → Authentication → Email Templates
2. Select "Confirm signup" template
3. Update the HTML with the template from `supabase/email_templates/confirm_signup.html`
4. The `{{ .ConfirmationURL }}` variable will be automatically replaced with the magic link
