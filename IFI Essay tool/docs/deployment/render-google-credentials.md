# Google Vision Credentials on Render

Render often truncates large env vars and Secret File pastes. **Use base64** for reliable setup.

## Option A: Base64 (Recommended)

1. **Generate base64 from your credentials file:**
   ```bash
   cd "IFI Essay tool"
   ./scripts/export_credentials_b64.sh
   ```
   Or manually:
   ```bash
   base64 -w0 credentials_vision.json   # Linux
   base64 -i credentials_vision.json | tr -d '\n'   # macOS
   ```

2. **Add to Render** (web + worker):
   - Key: `GOOGLE_CLOUD_VISION_CREDENTIALS_B64`
   - Value: paste the base64 output

3. **Remove** `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON` and Secret File if you had them.

## Option B: Secret File

1. Add Secret File `credentials_vision.json` in dashboard.
2. Set `GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/credentials_vision.json`
3. Paste the **full** JSON. If you get "unterminated string", the paste was truncated — use Option A instead.

## Option C: Raw JSON

Only if it fits without truncation. Minify and paste as single line:
```bash
python -c "import json; print(json.dumps(json.load(open('credentials_vision.json'))))"
```
