# OCR Providers - Quick Reference

## 🎯 **Recommended: EasyOCR (Free & Local)**

**Best for most users:** No setup, no API keys, runs locally!

```bash
# Already installed! Just use it:
./run.sh
# Select "easyocr" in dropdown
```

**First run:** Downloads models (~100MB, one-time)  
**Accuracy:** 85-90% for handwriting  
**Cost:** FREE forever  
**Privacy:** All local, no cloud

📚 **Full Guide:** See `EASYOCR_GUIDE.md`

---

# Google Cloud Vision OCR - Alternative Option

## 🚀 Quick Start (5 Steps)

### 1. Get Google Cloud Credentials
```bash
# Download service account JSON from Google Cloud Console
# Save as: essayflow-credentials.json
```

### 2. Set Environment Variable (Choose One Method)

**Method 1 - File Path (Local Development):**
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/essayflow-credentials.json"
```

**Method 2 - JSON Content (Docker/Cloud):**
```bash
export GOOGLE_CLOUD_VISION_CREDENTIALS_JSON=$(cat /path/to/essayflow-credentials.json)
```

### 3. Install Dependencies
```bash
cd essayflow
source .venv/bin/activate
pip install google-cloud-vision PyMuPDF
```

### 4. Run the App
```bash
streamlit run app.py
# OR
./run.sh
```

### 5. Use in UI
- Select **"google"** from OCR Provider dropdown
- Upload image or PDF
- Click "Run Processor"

---

## 📊 Quality Score Guide

| Score | Meaning | Action |
|-------|---------|--------|
| 0.90-1.00 | Excellent | Auto-approve |
| 0.75-0.89 | Good | Review field extraction |
| 0.60-0.74 | Fair | Manual review recommended |
| 0.00-0.59 | Poor | Re-scan or manual entry |

---

## 🔧 Troubleshooting

### "GOOGLE_APPLICATION_CREDENTIALS is not set"
```bash
# Method 1: File path
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your-key.json"

# OR Method 2: JSON content
export GOOGLE_CLOUD_VISION_CREDENTIALS_JSON=$(cat /path/to/your-key.json)

# Then restart Streamlit
```

### "Cloud Vision API has not been used"
1. Go to Google Cloud Console
2. Enable Cloud Vision API
3. Wait 2 minutes, try again

### "The caller does not have permission"
- Service account needs **Cloud Vision API User** role
- Regenerate key in Google Cloud Console

### PDF not processing
```bash
pip install PyMuPDF  # Make sure it's installed
```

---

## 💰 Pricing

- **Free:** First 1,000 requests/month
- **After:** $1.50 per 1,000 requests
- **Example:** 100 essays = FREE, 2,000 essays = $1.50

---

## 🎯 Supported Files

| Format | Support | Notes |
|--------|---------|-------|
| PNG | ✅ | Full support |
| JPG/JPEG | ✅ | Full support |
| PDF | ✅ | First page only (300 DPI) |

---

## 🔒 Security Checklist

- ✅ Add `*service-account*.json` to .gitignore
- ✅ Never commit credentials to git
- ✅ Use service account (not personal credentials)
- ✅ Rotate keys every 90 days
- ✅ Monitor API usage in Google Cloud Console

---

## 📚 Full Documentation

- **Setup Guide:** `GOOGLE_VISION_SETUP.md` (detailed instructions)
- **Implementation:** `GOOGLE_OCR_IMPLEMENTATION.md` (technical details)
- **General Usage:** `HOW_TO_RUN.md`

---

## 🆘 Support Links

- **Google Cloud Vision Docs:** https://cloud.google.com/vision/docs
- **Python Client:** https://googleapis.dev/python/vision/latest/
- **Pricing:** https://cloud.google.com/vision/pricing
- **Console:** https://console.cloud.google.com/

---

**Last Updated:** 2025-12-23

