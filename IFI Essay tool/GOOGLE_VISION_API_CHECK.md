# Google Cloud Vision API - Check & Fix Guide

## 🔍 If you received an email about Google Cloud Vision being disabled

The email usually means one of these issues:

### 1. **API Not Enabled** (Most Common)
   - **Check:** https://console.cloud.google.com/apis/library/vision.googleapis.com
   - **Fix:** Click "ENABLE" if it shows "API not enabled"
   - **Status should show:** ✅ "API enabled"

### 2. **Billing Not Enabled**
   - **Check:** https://console.cloud.google.com/billing
   - **Fix:** Enable billing on your Google Cloud project
   - **Note:** Google Cloud Vision has a free tier (first 1,000 units/month free)

### 3. **Service Account Missing Permissions**
   - **Check:** https://console.cloud.google.com/iam-admin/iam
   - **Find your service account** (the email from your credentials JSON)
   - **Verify it has:** `Cloud Vision API User` role
   - **Fix:** Click "Edit" → "Add Role" → Select "Cloud Vision API User"

### 4. **API Quota Exceeded**
   - **Check:** https://console.cloud.google.com/apis/api/vision.googleapis.com/quotas
   - **Fix:** 
     - Wait for quota to reset (usually monthly)
     - Or request quota increase if needed

### 5. **Invalid or Expired Credentials**
   - **Check:** Your `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON` environment variable
   - **Verify:** The JSON is valid and not expired
   - **Fix:** Generate new service account key if expired

## 🚀 Quick Fix Steps

### Step 1: Enable the API
1. Go to: https://console.cloud.google.com/apis/library/vision.googleapis.com
2. Select your project (the one from your credentials)
3. Click **"ENABLE"** button
4. Wait 1-2 minutes for activation

### Step 2: Verify Billing
1. Go to: https://console.cloud.google.com/billing
2. Make sure billing is enabled for your project
3. If not, add a billing account

### Step 3: Check Service Account Permissions
1. Go to: https://console.cloud.google.com/iam-admin/iam
2. Find your service account (from `client_email` in credentials JSON)
3. Click the pencil icon (Edit)
4. Click "ADD ANOTHER ROLE"
5. Select: **"Cloud Vision API User"**
6. Click "SAVE"

### Step 4: Test the API
After enabling, test with a simple request:
```bash
# If you have gcloud CLI installed
gcloud auth activate-service-account --key-file=your-credentials.json
gcloud services enable vision.googleapis.com
```

## 📧 What the Email Usually Says

The email typically says something like:
- "Cloud Vision API has been disabled"
- "API access has been revoked"
- "Billing account required"
- "Service account permissions missing"

## ✅ Verification Checklist

- [ ] Cloud Vision API is **ENABLED** in API Library
- [ ] Billing is **ENABLED** for the project
- [ ] Service account has **"Cloud Vision API User"** role
- [ ] Credentials JSON is valid and not expired
- [ ] Project has quota available (check quotas page)

## 🔗 Direct Links

- **Enable API:** https://console.cloud.google.com/apis/library/vision.googleapis.com
- **Check Billing:** https://console.cloud.google.com/billing
- **IAM Permissions:** https://console.cloud.google.com/iam-admin/iam
- **API Quotas:** https://console.cloud.google.com/apis/api/vision.googleapis.com/quotas
- **API Dashboard:** https://console.cloud.google.com/apis/dashboard

## 💡 After Fixing

1. **Wait 1-2 minutes** for changes to propagate
2. **Restart your application** (if running locally or in Docker)
3. **Try uploading a file again**
4. **Check logs** for any remaining errors

## 🆘 Still Not Working?

If you've done all the above and it's still failing:

1. **Check application logs** for specific error messages
2. **Verify credentials** are correctly set in environment variables
3. **Test API directly** using Google Cloud Console's "Try this API" feature
4. **Check project status** - make sure project is active and not suspended



