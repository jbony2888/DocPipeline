# Google Cloud Vision OCR Setup Guide

## Overview

EssayFlow now supports real handwriting OCR using **Google Cloud Vision API**. This guide explains how to set up and use it.

## What Was Implemented

### 1. **GoogleVisionOcrProvider** (`pipeline/ocr.py`)
- Uses Google Cloud Vision's `DOCUMENT_TEXT_DETECTION` feature
- Optimized for handwriting recognition
- Supports both images (PNG/JPG/JPEG) and PDFs
- For PDFs: renders first page to PNG at 300 DPI for better OCR accuracy

### 2. **OCR Quality Score** (Deterministic Confidence)
Since Google Cloud Vision doesn't always provide consistent confidence values, we compute a deterministic quality score (0-1) based on text characteristics:

**Formula:**
```python
alpha_ratio = letters / non_whitespace_chars
garbage_ratio = non_alphanumeric / non_whitespace_chars
score = (alpha_ratio * 0.8) + ((1 - garbage_ratio) * 0.2)
```

**Score Interpretation:**
- `0.9-1.0`: High quality (clean text, few special chars)
- `0.7-0.9`: Good quality (typical handwriting with punctuation)
- `0.5-0.7`: Moderate quality (may have numbers/symbols)
- `0.0-0.5`: Low quality (many errors or garbage characters)

### 3. **PDF Support via PyMuPDF**
- Automatically detects PDF files
- Renders first page to PNG at 300 DPI
- Sends rendered image to Vision API
- No manual conversion needed

---

## Setup Instructions

### Prerequisites
1. Google Cloud Platform account
2. Project with billing enabled
3. Cloud Vision API enabled

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Note your Project ID

### Step 2: Enable Cloud Vision API

1. In Google Cloud Console, go to **APIs & Services** > **Library**
2. Search for "Cloud Vision API"
3. Click **Enable**

### Step 3: Enable Billing

1. Go to **Billing** in Google Cloud Console
2. Link a billing account to your project
3. Cloud Vision API has a free tier:
   - First 1,000 units/month free for DOCUMENT_TEXT_DETECTION
   - After that: $1.50 per 1,000 units

### Step 4: Create Service Account & Download Credentials

1. Go to **IAM & Admin** > **Service Accounts**
2. Click **Create Service Account**
3. Name it (e.g., `essayflow-ocr`)
4. Grant role: **Cloud Vision API User**
5. Click **Done**
6. Click on the service account you created
7. Go to **Keys** tab
8. Click **Add Key** > **Create new key**
9. Choose **JSON** format
10. Download the JSON file (e.g., `essayflow-service-account.json`)
11. **Keep this file secure!** Never commit it to git.

### Step 5: Set Environment Variable

You can provide credentials in **two ways**. Choose the method that works best for your deployment scenario.

#### Method 1: File Path (Recommended for Local Development)

**On macOS/Linux:**
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/essayflow-service-account.json"
```

Add to `~/.zshrc` or `~/.bashrc` to make it permanent:
```bash
echo 'export GOOGLE_APPLICATION_CREDENTIALS="/path/to/essayflow-service-account.json"' >> ~/.zshrc
source ~/.zshrc
```

**On Windows (PowerShell):**
```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\essayflow-service-account.json"
```

For permanent:
```powershell
[System.Environment]::SetEnvironmentVariable('GOOGLE_APPLICATION_CREDENTIALS', 'C:\path\to\essayflow-service-account.json', 'User')
```

#### Method 2: JSON Content Directly (Recommended for Docker/Cloud Deployments)

This method is useful when you can't easily mount a credentials file (e.g., in containers, serverless, or cloud platforms).

**On macOS/Linux:**
```bash
# Load entire JSON file into environment variable
export GOOGLE_CLOUD_VISION_CREDENTIALS_JSON=$(cat /path/to/essayflow-service-account.json)
```

**Or provide JSON directly:**
```bash
export GOOGLE_CLOUD_VISION_CREDENTIALS_JSON='{"type":"service_account","project_id":"your-project",...}'
```

**On Windows (PowerShell):**
```powershell
# Load from file
$env:GOOGLE_CLOUD_VISION_CREDENTIALS_JSON = Get-Content -Raw -Path "C:\path\to\essayflow-service-account.json"
```

**In Docker/Kubernetes:**
```yaml
# Example: Kubernetes Secret
apiVersion: v1
kind: Secret
metadata:
  name: google-cloud-credentials
type: Opaque
stringData:
  credentials.json: |
    {
      "type": "service_account",
      "project_id": "your-project",
      ...
    }

# Then inject as env var in deployment:
env:
  - name: GOOGLE_CLOUD_VISION_CREDENTIALS_JSON
    valueFrom:
      secretKeyRef:
        name: google-cloud-credentials
        key: credentials.json
```

**Which method should I use?**
- **Local development:** Use Method 1 (file path) - easier to manage
- **Docker/containers:** Use Method 2 (JSON content) - no file mounting needed
- **Cloud platforms (AWS/Azure/GCP):** Use Method 2 with secrets manager
- **CI/CD pipelines:** Use Method 2 with encrypted secrets

### Step 6: Install Dependencies

Dependencies are already in `requirements.txt`:
```bash
cd essayflow
source .venv/bin/activate
pip install google-cloud-vision PyMuPDF
```

### Step 7: Run the Application

```bash
streamlit run app.py
```

---

## Using Google Cloud Vision OCR

1. **Start the app:**
   ```bash
   ./run.sh
   ```

2. **Select OCR Provider:**
   - Choose **"google"** from the dropdown (instead of "stub")

3. **Upload a file:**
   - Upload an image (PNG/JPG/JPEG) or PDF
   - Click **"Run Processor"**

4. **View results:**
   - Extracted text will appear
   - Quality score (confidence_avg) will be displayed
   - All artifacts will be saved

---

## Troubleshooting

### Error: "GOOGLE_APPLICATION_CREDENTIALS is not set"

**Solution:**
```bash
# Check if variable is set
echo $GOOGLE_APPLICATION_CREDENTIALS

# If empty, set it:
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your-service-account.json"

# Restart Streamlit
```

### Error: "Cloud Vision API has not been used in project..."

**Solution:**
1. Go to Google Cloud Console
2. Enable Cloud Vision API for your project
3. Wait 1-2 minutes for activation
4. Try again

### Error: "The caller does not have permission"

**Solution:**
1. Check service account has **Cloud Vision API User** role
2. Regenerate and download a new key if needed
3. Update `GOOGLE_APPLICATION_CREDENTIALS` path

### Error: "Billing must be enabled"

**Solution:**
1. Go to Google Cloud Console > Billing
2. Link a billing account to your project
3. Don't worry - first 1,000 requests/month are free!

### PDF Not Processing

**Solution:**
- Ensure PyMuPDF is installed: `pip install PyMuPDF`
- Check PDF is not corrupted
- Verify PDF has at least one page

---

## Cost Estimates

### Google Cloud Vision Pricing (as of 2024)

**DOCUMENT_TEXT_DETECTION:**
- First 1,000 units/month: **FREE**
- 1,001 - 5,000,000 units: $1.50 per 1,000 units
- 5,000,001+ units: $0.60 per 1,000 units

**Example Costs:**
- 100 essays/month: **FREE**
- 2,000 essays/month: $1.50
- 10,000 essays/month: $13.50

**Note:** One image = one unit. One PDF page = one unit.

---

## Architecture Notes

### Provider Pattern
The implementation follows the `OcrProvider` protocol pattern:

```python
class OcrProvider(Protocol):
    def process_image(self, image_path: str) -> OcrResult:
        ...
```

This makes it easy to add more providers (Azure, AWS Textract, etc.) in the future.

### Artifact Flow
1. **Input:** Image or PDF file path
2. **Processing:**
   - If PDF: render page 1 to PNG (300 DPI)
   - If image: read bytes directly
3. **API Call:** Send to Vision `document_text_detection`
4. **Output:** `OcrResult` with:
   - `text`: Full extracted text
   - `confidence_avg`: Computed quality score (0-1)
   - `lines`: List of text lines
5. **Artifacts:** Same as stub (ocr.json, raw_text.txt, etc.)

### No Schema Changes
The existing pipeline stages (segmentation, extraction, validation) work unchanged. They simply receive better OCR results when using Google Cloud Vision.

---

## Testing

### Test with Stub (No Credentials Needed)
```bash
# Select "stub" provider in UI
# Upload any file
# Click "Run Processor"
```

### Test with Google Cloud Vision
```bash
# Set credentials
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"

# Run app
streamlit run app.py

# Select "google" provider
# Upload a handwritten essay image or PDF
# Click "Run Processor"
```

### Quality Score Examples

Upload these to see quality scores:
- **Clean typed text:** Score ~0.95-1.0
- **Good handwriting:** Score ~0.75-0.90
- **Messy handwriting:** Score ~0.60-0.75
- **Poor quality scan:** Score ~0.40-0.60

---

## Security Best Practices

1. **Never commit credentials to git:**
   ```bash
   # Add to .gitignore
   echo "*service-account*.json" >> .gitignore
   echo ".env" >> .gitignore
   ```

2. **Rotate keys periodically:**
   - Create new service account key every 90 days
   - Delete old keys

3. **Use least privilege:**
   - Service account should only have **Cloud Vision API User** role
   - No Owner or Editor roles needed

4. **Monitor usage:**
   - Check Google Cloud Console > APIs & Services > Dashboard
   - Set up budget alerts

---

## Comparison: Stub vs Google Cloud Vision

| Feature | Stub | Google Cloud Vision |
|---------|------|---------------------|
| Setup | None | Requires GCP account + credentials |
| Cost | Free | $1.50 per 1,000 after free tier |
| Accuracy | N/A (fake data) | High (90%+ for good handwriting) |
| Handwriting | Simulated | Real recognition |
| PDF Support | Yes (fake) | Yes (renders page 1) |
| Quality Score | Fixed 0.65 | Computed 0-1 |
| Use Case | Testing/Demo | Production |

---

## Next Steps

After getting Google Cloud Vision working:

1. **Test with real handwritten essays**
2. **Evaluate quality scores** - adjust validation thresholds if needed
3. **Monitor costs** - set budget alerts in GCP
4. **Consider batch processing** - for large volumes, batch API calls
5. **Explore other providers** - Azure Computer Vision, AWS Textract, etc.

---

## Support

- **Google Cloud Vision Docs:** https://cloud.google.com/vision/docs
- **Python Client Docs:** https://googleapis.dev/python/vision/latest/
- **Pricing:** https://cloud.google.com/vision/pricing

---

**Status:** ✅ Fully implemented and tested
**Last Updated:** 2025-12-23

