# Copy This for Render Deployment

## Google Cloud Vision Credentials

**⚠️ IMPORTANT: You need to provide your own Google Cloud Vision service account JSON.**

To get your credentials:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Enable the Cloud Vision API
4. Create a service account: IAM & Admin → Service Accounts → Create Service Account
5. Download the JSON key file
6. Copy the **entire JSON content** (everything from `{` to `}`)

**Example format** (⚠️ THIS IS FAKE - DO NOT USE - REPLACE ALL VALUES WITH YOUR ACTUAL CREDENTIALS ⚠️):
```
{
  "type": "service_account",
  "project_id": "YOUR-PROJECT-ID-HERE",
  "private_key_id": "FAKE-KEY-ID-DO-NOT-USE",
  "private_key": "-----BEGIN PRIVATE KEY-----\nFAKE_PRIVATE_KEY_CONTENT_REPLACE_THIS\n-----END PRIVATE KEY-----\n",
  "client_email": "your-service-account@YOUR-PROJECT-ID.iam.gserviceaccount.com",
  "client_id": "123456789012345678901",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40YOUR-PROJECT-ID.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}
```

**⚠️ IMPORTANT:** The above is a template/example. Every value marked with "YOUR-", "FAKE-", or placeholder text must be replaced with your actual credentials from Google Cloud Console.

---

## Step-by-Step Instructions

### 1. Go to Render Dashboard
- Visit: https://dashboard.render.com
- Select your service: `ifi-essay-gateway`

### 2. Add Google Cloud Vision Variable
- Click: **"Environment"** tab (left sidebar)
- Click: **"Add Environment Variable"**
- **Key**: `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON`
- **Value**: Paste your **entire** Google Cloud service account JSON string (starts with `{"type":"service_account"` and ends with `"universe_domain":"googleapis.com"}`)
  - Open your downloaded JSON key file
  - Copy the entire contents (everything from `{` to `}`)
  - Paste it as a single line (no line breaks)
- Click: **"Save Changes"**

### 3. Add Groq API Key
- Click: **"Add Environment Variable"** again
- **Key**: `GROQ_API_KEY`
- **Value**: Your Groq API key (get it from https://console.groq.com/keys)
- Click: **"Save Changes"**

### 4. Deploy
- Your service will automatically redeploy, OR
- Click **"Manual Deploy"** → **"Clear build cache & deploy"**

---

## Quick Checklist

- [ ] Copied the entire JSON string (everything from `{` to `}`)
- [ ] Pasted into Render dashboard as `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON`
- [ ] Added `GROQ_API_KEY` with your Groq API key
- [ ] Saved both variables
- [ ] Redeployed service

---

**That's it!** Your app should now work on Render. ✅

