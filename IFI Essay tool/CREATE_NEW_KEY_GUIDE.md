# Create New Service Account Key - Step by Step

## ✅ RECOMMENDED: Create New Key for Existing Account

**You don't need a new service account** - just create a new **key** for the existing one.

### Step 1: Go to Service Accounts Page

1. Open: https://console.cloud.google.com/iam-admin/serviceaccounts?project=youtube-ai-tool-478918
2. Make sure you're in the correct project: `youtube-ai-tool-478918`

### Step 2: Find Your Service Account

1. Look for: `essay-forms@youtube-ai-tool-478918.iam.gserviceaccount.com`
2. Click on the service account name to open details

### Step 3: Create New Key

1. Click the **"KEYS"** tab at the top
2. Click **"ADD KEY"** button
3. Select **"Create new key"**
4. Choose **"JSON"** format
5. Click **"CREATE"**
6. The JSON file will download automatically

### Step 4: Delete Old Key

1. Still in the **"KEYS"** tab
2. Find the key with ID: `1941d902d881dcaf66ff970127926db540894cb0`
3. Click the **trash icon** (🗑️) next to it
4. Confirm deletion

### Step 5: Update Your Environment Variables

#### For Local Development (.env file):

```bash
# Open your .env file and update:
GOOGLE_CLOUD_VISION_CREDENTIALS_JSON='<paste entire JSON content from new key file>'
```

**To get the JSON content:**
```bash
# If you downloaded the key file:
cat /path/to/downloaded-key.json

# Copy the entire JSON (everything between { and })
```

#### For Render (Production):

1. Go to Render Dashboard → Your Service → Environment
2. Find `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON`
3. Click "Edit" or "Update"
4. Paste the entire JSON content from the new key file
5. Click "Save Changes"
6. **Redeploy** your service

#### For Docker (docker-compose.yml):

Update your `.env` file or environment variables:
```bash
export GOOGLE_CLOUD_VISION_CREDENTIALS_JSON='<paste JSON here>'
```

### Step 6: Test

1. Restart your application
2. Try uploading a file
3. Check that OCR processing works

---

## ⚠️ Alternative: Create New Service Account (Only if Needed)

**Only do this if:**
- The existing service account is also disabled/compromised
- You want a completely fresh start
- You want better organization

### If You Need a New Service Account:

1. **Create Service Account:**
   - Go to: https://console.cloud.google.com/iam-admin/serviceaccounts?project=youtube-ai-tool-478918
   - Click **"CREATE SERVICE ACCOUNT"**
   - Name: `essay-forms-v2` (or similar)
   - Click **"CREATE AND CONTINUE"**

2. **Grant Permissions:**
   - Add role: **"Cloud Vision API User"**
   - Click **"CONTINUE"** → **"DONE"**

3. **Create Key:**
   - Click on the new service account
   - Go to **"KEYS"** tab
   - Click **"ADD KEY"** → **"Create new key"** → **"JSON"**
   - Download the key

4. **Update Code (if service account email changed):**
   - No code changes needed if you just update the JSON key
   - The JSON contains everything needed

5. **Update Environment Variables:**
   - Same as Step 5 above, but use the new key JSON

---

## 🔍 Verify the Key Works

After updating, test with:

```python
# Quick test script
import os
import json
from google.cloud import vision
from google.oauth2 import service_account

# Load credentials
creds_json = os.environ.get('GOOGLE_CLOUD_VISION_CREDENTIALS_JSON')
if creds_json:
    creds_dict = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(creds_dict)
    client = vision.ImageAnnotatorClient(credentials=credentials)
    print("✅ Google Cloud Vision client initialized successfully!")
else:
    print("❌ GOOGLE_CLOUD_VISION_CREDENTIALS_JSON not set")
```

---

## 📝 Quick Checklist

- [ ] Opened Google Cloud Console → Service Accounts
- [ ] Found `essay-forms@youtube-ai-tool-478918.iam.gserviceaccount.com`
- [ ] Created new JSON key
- [ ] Downloaded the new key file
- [ ] Deleted old key (ID: `1941d902d881dcaf66ff970127926db540894cb0`)
- [ ] Updated `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON` in `.env` (local)
- [ ] Updated `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON` in Render dashboard
- [ ] Restarted application
- [ ] Tested file upload
- [ ] Verified OCR processing works

---

## 🆘 Troubleshooting

### "Service account not found"
- Make sure you're in the correct project: `youtube-ai-tool-478918`
- Check the project selector in the top bar

### "Permission denied"
- Make sure you have "Service Account Admin" or "Owner" role
- Contact project owner if needed

### "Key creation failed"
- Check that billing is enabled
- Verify Cloud Vision API is enabled
- Try again in a few minutes

### "Still getting errors after updating"
- Make sure you copied the **entire** JSON (including all `{}` brackets)
- Verify no extra spaces or line breaks
- Restart your application completely
- Check application logs for specific error messages

