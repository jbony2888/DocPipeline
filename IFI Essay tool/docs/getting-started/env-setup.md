# Environment Variables Setup Guide

## ⚠️ Security Warning

**NEVER commit actual API keys or credentials to Git!**

- Use `.env` files or environment variables
- Add credential files to `.gitignore`
- Use platform-specific secret management for deployments

---

## Quick Setup

### Option 1: Use Template Files (Recommended)

1. **Copy the template:**
   ```bash
   cp env.example.yaml env.yaml
   ```

2. **Edit `env.yaml`** with your actual values
   - This file is gitignored (won't be committed)
   - Use as reference when setting up deployment

3. **For local development:**
   - Export variables manually, OR
   - Use a `.env` loader (python-dotenv)

### Option 2: Export Directly (Local Development)

```bash
# Google Cloud Vision (as JSON string)
export GOOGLE_CLOUD_VISION_CREDENTIALS_JSON='{"type":"service_account",...}'

# Groq API Key
export GROQ_API_KEY='gsk_your_key_here'
```

### Option 3: Use Platform Secrets (Cloud Deployment)

Each platform has its own secrets management:
- **Streamlit Cloud**: Dashboard → Settings → Secrets
- **Render**: Dashboard → Environment Variables
- **Railway**: Dashboard → Variables
- **Fly.io**: `fly secrets set KEY=value`

---

## Required Environment Variables

### 1. GOOGLE_CLOUD_VISION_CREDENTIALS_JSON

**Format:** Single-line JSON string

**How to get:**
1. Go to Google Cloud Console
2. IAM & Admin → Service Accounts
3. Create/download service account key (JSON)
4. Copy entire JSON content
5. Convert to single line (replace newlines with `\n`)

**Example:**
```bash
# Convert multi-line JSON to single line
cat credentials.json | jq -c

# Or manually: remove all actual newlines, keep \n in private_key
```

**Local alternative:** Use file path instead:
```bash
export GOOGLE_APPLICATION_CREDENTIALS='/path/to/credentials.json'
```

### 2. GROQ_API_KEY

**Format:** String starting with `gsk_`

**How to get:**
1. Go to https://console.groq.com/keys
2. Sign up/login
3. Create API key
4. Copy key (starts with `gsk_`)

**Example:**
```bash
export GROQ_API_KEY='gsk_YOUR_GROQ_API_KEY'
```

---

## Platform-Specific Setup

### Streamlit Cloud

1. Go to app dashboard
2. Settings → Secrets
3. Add each variable:
   ```
   GOOGLE_CLOUD_VISION_CREDENTIALS_JSON = {"type":"service_account",...}
   GROQ_API_KEY = gsk_your_key_here
   ```

### Render

1. Go to service dashboard
2. Environment tab
3. Add each variable:
   - Key: `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON`
   - Value: `{"type":"service_account",...}`

### Railway

1. Go to project dashboard
2. Variables tab
3. Add each variable (or use `railway variables` CLI)

### Fly.io

```bash
fly secrets set GOOGLE_CLOUD_VISION_CREDENTIALS_JSON='{"type":"service_account",...}'
fly secrets set GROQ_API_KEY='gsk_your_key_here'
```

### Local Development (Python)

**Option A: Export before running**
```bash
export GOOGLE_CLOUD_VISION_CREDENTIALS_JSON='...'
export GROQ_API_KEY='gsk_...'
streamlit run app.py
```

**Option B: Use python-dotenv**

1. Install: `pip install python-dotenv`
2. Create `.env` file (gitignored):
   ```
   GOOGLE_CLOUD_VISION_CREDENTIALS_JSON={"type":"service_account",...}
   GROQ_API_KEY=gsk_your_key_here
   ```
3. Load in `app.py`:
   ```python
   from dotenv import load_dotenv
   load_dotenv()
   ```

---

## Testing Your Setup

### Verify Variables Are Set

```python
import os

# Check Google Vision
google_creds = os.environ.get("GOOGLE_CLOUD_VISION_CREDENTIALS_JSON") or \
               os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
if google_creds:
    print("✅ Google Vision credentials found")
else:
    print("❌ Google Vision credentials missing")

# Check Groq
groq_key = os.environ.get("GROQ_API_KEY")
if groq_key:
    print("✅ Groq API key found")
else:
    print("❌ Groq API key missing")
```

### Test in App

1. Run your Streamlit app
2. Check the status message at top
3. Should show: "✅ Ready to Process"

---

## Troubleshooting

### "Credentials not found" Error

**Problem:** App can't find credentials  
**Solution:**
1. Verify variable names are correct (case-sensitive)
2. Check JSON format (valid, single-line)
3. For local: Verify variables exported in same shell
4. For cloud: Verify set in platform dashboard

### "Invalid JSON" Error

**Problem:** Google credentials JSON invalid  
**Solution:**
1. Verify JSON is valid (test with `jq` or online validator)
2. Ensure single-line (no actual newlines)
3. Private key should have `\n` not actual newlines
4. Wrap entire JSON in quotes if setting as string

### App Shows "Setup Required"

**Problem:** App detects missing credentials  
**Solution:**
1. Check environment variables are set
2. Restart app after setting variables
3. Verify variable names match exactly

---

## Best Practices

1. ✅ **Use platform secrets management** (not files in repo)
2. ✅ **Rotate keys regularly** (every 90 days recommended)
3. ✅ **Use least-privilege IAM** (service account with only Vision API access)
4. ✅ **Monitor usage** (check API usage in Google Cloud Console)
5. ✅ **Never log credentials** (don't print env vars in logs)

---

## File Reference

- `env.example.yaml` - Template with placeholder values (safe to commit)
- `env.yaml.template` - Detailed template with instructions
- `.env` - Your actual values (gitignored, never commit!)
- `.gitignore` - Ensures credential files aren't committed

---

**Last Updated:** December 2024





