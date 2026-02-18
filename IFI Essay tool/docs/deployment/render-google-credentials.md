# Google Vision Credentials on Render

The JSON credentials for Google Cloud Vision can be large and fragile when pasted into environment variables (truncation, escaping). **Use a Secret File** instead for reliable production use.

## Option A: Secret File (Recommended)

1. **Add Secret File in Render Dashboard**
   - Open your **web service** → Environment
   - Add **Secret File** (not Environment Variable)
   - Filename: `credentials_vision.json`
   - Paste the full service account JSON (can be multi-line; Render stores it as a file)

2. **Add to Worker as well**
   - Open your **worker service** → Environment
   - Add the same Secret File: `credentials_vision.json`

3. **Set path env var** (or let code use default)
   - Add: `GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/credentials_vision.json`
   - Render mounts secret files at `/etc/secrets/<filename>`

The app will load credentials from the file. You can **remove** `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON` from both services if you use this.

## Option B: Environment Variable

If you prefer the env var approach, the value **must be a single line** with no line breaks:

1. Minify your JSON:
   ```bash
   python -c "import json; print(json.dumps(json.load(open('credentials_vision.json'))))"
   ```

2. Copy the output (single long line) and paste into `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON` in the Render dashboard.

3. Do **not** paste multi-line or pretty-printed JSON — it often breaks with "unterminated string" or similar errors.
