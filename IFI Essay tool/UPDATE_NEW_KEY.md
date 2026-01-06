# Update New Service Account Key

## ✅ You Have Your New Key!

Now you need to update it in your environment variables.

## ⚠️ CRITICAL: Never Commit This Key to Git!

The key you just received is **sensitive** and should **NEVER** be committed to your repository.

## Step 1: Update Local .env File

1. Open your `.env` file in the project root
2. Find the line: `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON=`
3. Replace the value with your new JSON (as a single line, or use the format below)

**Format for .env file:**
```bash
GOOGLE_CLOUD_VISION_CREDENTIALS_JSON='{"type":"service_account","project_id":"YOUR_PROJECT_ID",...}'
```

**Important:** 
- Use single quotes around the entire JSON
- Keep it as one line (or escape newlines properly)
- Make sure `.env` is in `.gitignore` (it already is ✅)

## Step 2: Update Render Dashboard (Production)

1. Go to: https://dashboard.render.com
2. Navigate to your Flask service
3. Go to **"Environment"** tab
4. Find `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON`
5. Click **"Edit"** or **"Update"**
6. Paste the **entire JSON** as a single line
7. Click **"Save Changes"**
8. **Redeploy** your service (or it will auto-redeploy)

**Format for Render:**
- Paste the entire JSON as one continuous string
- No line breaks
- Render will handle the JSON parsing

## Step 3: Update Docker (if using docker-compose)

If you're using Docker locally:

1. Update your `.env` file (same as Step 1)
2. Restart Docker containers:
   ```bash
   docker-compose down
   docker-compose up -d
   ```

## Step 4: Test

1. **Restart your application** (if running locally)
2. **Try uploading a file**
3. **Check that OCR processing works**

## 🔍 Verify It's Working

After updating, you should see:
- ✅ File uploads succeed
- ✅ OCR processing completes
- ✅ No "API disabled" errors
- ✅ No "authentication failed" errors

## 🆘 Troubleshooting

### "Still getting errors"
- Make sure you copied the **entire** JSON (including all `{}` brackets)
- Verify no extra spaces or line breaks in the JSON
- Restart your application completely
- Check application logs for specific errors

### "Invalid JSON error"
- Make sure the JSON is on a single line in `.env`
- Or properly escape newlines if using multi-line
- Verify all quotes are properly escaped

### "Permission denied"
- Make sure the service account has "Cloud Vision API User" role
- Check that Cloud Vision API is enabled in Google Cloud Console

## ✅ Security Checklist

- [ ] Updated `.env` file (local)
- [ ] Updated Render dashboard (production)
- [ ] Verified `.env` is in `.gitignore` ✅ (already done)
- [ ] Did NOT commit the key to git
- [ ] Tested upload functionality
- [ ] Deleted old key from Google Cloud Console (optional but recommended)

## 📝 Quick Copy-Paste Format

For your `.env` file, use this format (replace with your actual key):

```bash
GOOGLE_CLOUD_VISION_CREDENTIALS_JSON='{"type":"service_account","project_id":"YOUR_PROJECT_ID","private_key_id":"YOUR_PRIVATE_KEY_ID","private_key":"-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY_HERE\n-----END PRIVATE KEY-----\n","client_email":"YOUR_SERVICE_ACCOUNT@YOUR_PROJECT.iam.gserviceaccount.com","client_id":"YOUR_CLIENT_ID","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":"https://www.googleapis.com/robot/v1/metadata/x509/YOUR_SERVICE_ACCOUNT%40YOUR_PROJECT.iam.gserviceaccount.com","universe_domain":"googleapis.com"}'
```

**Note:** Replace `\n...\n` with the actual private key content (keep the `\n` escape sequences).

