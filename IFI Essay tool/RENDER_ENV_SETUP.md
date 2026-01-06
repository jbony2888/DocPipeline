# Render Environment Variables Setup Guide

## Quick Setup for Render

Render uses **dashboard environment variables**, not YAML files directly. Follow these steps:

---

## Step 1: Prepare Google Cloud Vision Credentials

### Option A: Use Helper Script (Recommended)

```bash
cd "/Users/jerrybony/Documents/GitHub/DocPipeline/IFI Essay tool"

# Run the helper script
python scripts/prepare_render_env.py /path/to/your/google-credentials.json

# Example (replace with your own credentials file path):
python scripts/prepare_render_env.py ~/path/to/your-google-credentials.json
```

**What it does:**
- ✅ Formats your JSON to single-line string
- ✅ Validates the JSON format
- ✅ Saves to `render_google_creds.txt` for easy copy/paste
- ✅ Prints step-by-step instructions

### Option B: Manual Format

If you prefer to do it manually:

```bash
# Mac/Linux - Convert to single line
cat your-credentials.json | jq -c

# Or use Python
python -c "import json; print(json.dumps(json.load(open('your-credentials.json')), separators=(',', ':')))"
```

**Result:** Single-line JSON string like:
```
{"type":"service_account","project_id":"your-project","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",...}
```

---

## Step 2: Set Variables in Render Dashboard

1. **Go to**: https://dashboard.render.com
2. **Select**: Your `ifi-essay-gateway` service
3. **Click**: "Environment" tab (left sidebar)
4. **Click**: "Add Environment Variable" button

### Variable 1: Google Cloud Vision

- **Key**: `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON`
- **Value**: Paste the single-line JSON from Step 1
  - Copy the entire string (should start with `{"type":"service_account"`)
  - Paste into the Value field
  - Click "Save Changes"

### Variable 2: Groq API Key

- **Key**: `GROQ_API_KEY`
- **Value**: Your Groq API key (starts with `gsk_`)
  - Example: `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`
  - Click "Save Changes"

---

## Step 3: Verify Setup

After adding variables:

1. **Scroll down** to see all environment variables
2. **Verify** both variables are listed:
   - ✅ `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON` (Value hidden with dots)
   - ✅ `GROQ_API_KEY` (Value hidden with dots)

3. **Redeploy** (if service was already created):
   - Click "Manual Deploy" → "Clear build cache & deploy"

---

## Testing

1. **Wait** for deployment to complete
2. **Open** your Render app URL
3. **Check** the app - should show:
   - "✅ Ready to Process - Google Vision and enhanced processing are both configured."

If you see errors:
- Check Render logs (Logs tab)
- Verify JSON format (must be valid JSON)
- Verify keys are correct

---

## Important Notes

### About render.yaml

The `render.yaml` file defines your service configuration, but:
- ✅ Service settings (build command, start command) come from YAML
- ❌ **Environment variables with secrets should be set in dashboard** (not in YAML)

### Why Dashboard for Secrets?

- ✅ More secure (encrypted storage)
- ✅ Easy to update without redeploying
- ✅ Can rotate keys independently
- ✅ Render best practice

### File Format Requirements

**Google Cloud JSON must be:**
- ✅ Valid JSON
- ✅ Single line (no actual newlines)
- ✅ Private key can have `\n` (will be escaped correctly)
- ✅ Entire string in quotes when pasting

**Example of correct format:**
```json
{"type":"service_account","project_id":"my-project","private_key":"-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC...\n-----END PRIVATE KEY-----\n","client_email":"..."}
```

---

## Troubleshooting

### "Invalid JSON" Error

**Problem:** Render shows JSON parsing error  
**Solution:**
1. Use the helper script: `python scripts/prepare_render_env.py your-credentials.json`
2. Verify no line breaks in the string
3. Ensure private key has `\n` not actual newlines

### Variables Not Showing in App

**Problem:** App can't find environment variables  
**Solution:**
1. Verify variables saved in dashboard (check Environment tab)
2. Redeploy service after adding variables
3. Check variable names match exactly (case-sensitive)

### Credentials File Not Found

**Problem:** Helper script can't find your credentials file  
**Solution:**
1. Use full path: `/Users/jerrybony/Downloads/your-file.json`
2. Or navigate to file location first: `cd /path/to/file && python ../scripts/prepare_render_env.py filename.json`

---

## Quick Reference

```bash
# 1. Prepare credentials
python scripts/prepare_render_env.py your-credentials.json

# 2. Copy output to Render dashboard
#    - Key: GOOGLE_CLOUD_VISION_CREDENTIALS_JSON
#    - Value: [paste from render_google_creds.txt or script output]

# 3. Add Groq key in dashboard
#    - Key: GROQ_API_KEY  
#    - Value: gsk_your_key_here

# 4. Deploy!
```

---

**Last Updated:** December 2024

