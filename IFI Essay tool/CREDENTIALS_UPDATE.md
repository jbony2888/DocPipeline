# Google Cloud Vision Credentials Update

## What Changed

Added support for providing Google Cloud Vision credentials as **JSON content directly** via environment variable, in addition to the existing file path method.

---

## Two Ways to Provide Credentials

### Method 1: File Path (Original - Still Supported)

**Best for:** Local development, manual setup

**How it works:**
- Store credentials in a JSON file
- Set `GOOGLE_APPLICATION_CREDENTIALS` to the file path
- Google client loads credentials from the file

**Example:**
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
```

**Pros:**
- ✅ Standard Google Cloud approach
- ✅ Easy to manage locally
- ✅ Credentials file can have restricted permissions

**Cons:**
- ❌ Requires file system access
- ❌ Harder to use in containerized environments

---

### Method 2: JSON Content (New!)

**Best for:** Docker, Kubernetes, serverless, CI/CD, cloud deployments

**How it works:**
- Store credentials JSON content in environment variable
- Set `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON` with the JSON content
- Google client loads credentials directly from the env var

**Example:**
```bash
# Load from file into env var
export GOOGLE_CLOUD_VISION_CREDENTIALS_JSON=$(cat service-account.json)

# Or provide JSON directly
export GOOGLE_CLOUD_VISION_CREDENTIALS_JSON='{"type":"service_account","project_id":"...",...}'
```

**Pros:**
- ✅ No file system needed
- ✅ Perfect for containers/serverless
- ✅ Easy to inject from secrets managers
- ✅ Works with CI/CD pipelines

**Cons:**
- ❌ Credentials in environment (less secure if env exposed)
- ❌ Longer environment variable

---

## Implementation Details

### Priority Order

The `GoogleVisionOcrProvider` checks credentials in this order:

1. **First:** Check for `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON`
   - If set: Parse JSON and load credentials
   - If valid: Use these credentials

2. **Second:** Fall back to `GOOGLE_APPLICATION_CREDENTIALS`
   - Uses standard Google Cloud credentials chain
   - Loads from file path

3. **Third:** Google's default credential chain
   - Application Default Credentials (ADC)
   - Metadata server (if running on GCP)

### Code Changes

**Before:**
```python
def __init__(self):
    from google.cloud import vision
    self.client = vision.ImageAnnotatorClient()
```

**After:**
```python
def __init__(self):
    from google.cloud import vision
    from google.oauth2 import service_account
    
    credentials_json = os.environ.get('GOOGLE_CLOUD_VISION_CREDENTIALS_JSON')
    
    if credentials_json:
        # Load from JSON content
        credentials_dict = json.loads(credentials_json)
        credentials = service_account.Credentials.from_service_account_info(
            credentials_dict
        )
        self.client = vision.ImageAnnotatorClient(credentials=credentials)
    else:
        # Fall back to standard credentials chain
        self.client = vision.ImageAnnotatorClient()
```

---

## Use Cases

### Local Development
```bash
# Download credentials from Google Cloud Console
# Save as: ~/gcloud/essayflow-key.json

export GOOGLE_APPLICATION_CREDENTIALS="$HOME/gcloud/essayflow-key.json"
streamlit run app.py
```

### Docker Container
```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt

# Credentials injected at runtime
CMD ["streamlit", "run", "app.py"]
```

```bash
# Run with credentials from secret
docker run -e GOOGLE_CLOUD_VISION_CREDENTIALS_JSON="$(cat key.json)" essayflow
```

### Kubernetes Deployment
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: gcp-credentials
type: Opaque
stringData:
  key.json: |
    {
      "type": "service_account",
      "project_id": "your-project",
      ...
    }
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: essayflow
spec:
  template:
    spec:
      containers:
      - name: app
        image: essayflow:latest
        env:
        - name: GOOGLE_CLOUD_VISION_CREDENTIALS_JSON
          valueFrom:
            secretKeyRef:
              name: gcp-credentials
              key: key.json
```

### AWS ECS/Fargate
```json
{
  "containerDefinitions": [{
    "name": "essayflow",
    "image": "essayflow:latest",
    "secrets": [{
      "name": "GOOGLE_CLOUD_VISION_CREDENTIALS_JSON",
      "valueFrom": "arn:aws:secretsmanager:region:account:secret:gcp-credentials"
    }]
  }]
}
```

### GitHub Actions CI/CD
```yaml
# .github/workflows/test.yml
name: Test OCR
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Test with Google Cloud Vision
        env:
          GOOGLE_CLOUD_VISION_CREDENTIALS_JSON: ${{ secrets.GCP_CREDENTIALS }}
        run: python -m pytest tests/
```

---

## Security Best Practices

### ✅ DO

1. **Use secrets managers in production:**
   - AWS Secrets Manager
   - Azure Key Vault
   - GCP Secret Manager
   - HashiCorp Vault

2. **Inject at runtime:**
   ```bash
   # Good: Load from secure source
   export GOOGLE_CLOUD_VISION_CREDENTIALS_JSON=$(aws secretsmanager get-secret-value --secret-id gcp-creds --query SecretString --output text)
   ```

3. **Rotate credentials regularly:**
   - Create new service account key every 90 days
   - Delete old keys immediately

4. **Use least privilege:**
   - Service account only needs "Cloud Vision API User" role
   - No Owner/Editor roles

5. **Monitor usage:**
   - Check Google Cloud Console for API usage
   - Set up alerts for unusual activity

### ❌ DON'T

1. **Never commit credentials to git:**
   ```bash
   # Add to .gitignore
   *service-account*.json
   .env
   credentials.json
   ```

2. **Never hard-code credentials:**
   ```python
   # BAD! Never do this!
   credentials_json = '{"type":"service_account",...}'
   ```

3. **Never log or print credentials:**
   ```python
   # BAD!
   print(f"Credentials: {credentials_json}")
   logging.info(f"Using credentials: {credentials}")
   ```

4. **Don't expose environment in logs:**
   ```bash
   # BAD!
   env  # Shows all env vars including credentials
   ```

5. **Don't use personal credentials:**
   - Always use service accounts
   - Never use your personal Google account credentials

---

## Migration Guide

### If You're Already Using File Path Method

**No changes needed!** The file path method still works exactly the same. The new JSON content method is an additional option, not a replacement.

```bash
# This still works perfectly
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
streamlit run app.py
```

### If You Want to Switch to JSON Content Method

```bash
# Old way (still works)
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"

# New way (alternative)
export GOOGLE_CLOUD_VISION_CREDENTIALS_JSON=$(cat /path/to/key.json)

# Pick one method, not both
# If both are set, JSON content takes priority
```

### For Docker/Kubernetes Users

This update makes deployment much easier:

**Before (required file mounting):**
```bash
docker run -v /path/to/key.json:/app/key.json \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/key.json \
  essayflow
```

**After (no file mounting needed):**
```bash
docker run -e GOOGLE_CLOUD_VISION_CREDENTIALS_JSON="$(cat key.json)" \
  essayflow
```

---

## Testing

### Test Method 1 (File Path)
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
streamlit run app.py
# Select "google" provider in UI, upload file
```

### Test Method 2 (JSON Content)
```bash
export GOOGLE_CLOUD_VISION_CREDENTIALS_JSON=$(cat /path/to/key.json)
streamlit run app.py
# Select "google" provider in UI, upload file
```

### Verify Which Method Is Being Used

Check the logs or test script output - it will show which credential method was used.

---

## Troubleshooting

### Both env vars are set - which one is used?

**JSON content takes priority.** If `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON` is set, it will be used instead of `GOOGLE_APPLICATION_CREDENTIALS`.

### "Invalid JSON in GOOGLE_CLOUD_VISION_CREDENTIALS_JSON"

The JSON is malformed. Common issues:
- Extra quotes or escaping
- Newlines not properly handled
- File encoding issues

**Solution:**
```bash
# Make sure JSON is valid
cat key.json | jq .  # Test with jq

# Load properly
export GOOGLE_CLOUD_VISION_CREDENTIALS_JSON=$(cat key.json)
```

### Works locally but not in Docker

**Issue:** Credentials not passed to container

**Solution:**
```bash
# Pass as build arg (for multi-stage builds)
docker build --build-arg GCP_CREDS="$(cat key.json)" .

# Or pass at runtime (recommended)
docker run -e GOOGLE_CLOUD_VISION_CREDENTIALS_JSON="$(cat key.json)" essayflow
```

### Credentials work but API calls fail

**Not a credentials issue.** Check:
1. Cloud Vision API is enabled
2. Service account has correct role
3. Billing is enabled
4. API quotas not exceeded

---

## Files Modified

1. **`pipeline/ocr.py`**
   - Added support for `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON`
   - Updated `__init__` to check both credential methods
   - Improved error messages

2. **`app.py`**
   - Updated comments to mention both methods
   - Updated error messages to show both options

3. **Documentation:**
   - `GOOGLE_VISION_SETUP.md` - Added Method 2 instructions
   - `QUICK_REFERENCE_GOOGLE_OCR.md` - Updated quick start
   - `CREDENTIALS_UPDATE.md` - This document

---

## Summary

### What You Get

- ✅ **Flexibility:** Choose file path OR JSON content
- ✅ **Container-friendly:** No file mounting needed
- ✅ **Secrets manager compatible:** Easy to inject from vaults
- ✅ **Backward compatible:** Existing setups work unchanged
- ✅ **Production-ready:** Tested and documented

### Recommendation

- **Local dev:** Use `GOOGLE_APPLICATION_CREDENTIALS` (file path)
- **Production/Cloud:** Use `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON` (JSON content)
- **CI/CD:** Use `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON` with secrets

---

**Last Updated:** 2025-12-23
**Version:** 1.1
**Status:** Production-ready


