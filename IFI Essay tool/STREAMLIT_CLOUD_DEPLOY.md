# Deploying EssayFlow to Streamlit Cloud

## 🎯 **Perfect for Demos!**

Streamlit Cloud is great for quick demos and sharing your app with a public URL.

---

## ⚠️ **Important: OCR Provider Choice**

Streamlit Cloud **FREE tier has 1GB RAM** - this affects which OCR you can use:

| OCR Provider | Streamlit Cloud Free | Recommended |
|--------------|---------------------|-------------|
| **Stub** | ✅ Perfect | **YES - for UI demos** |
| **Google Cloud Vision** | ✅ Works fine | **YES - if you have credentials** |
| **EasyOCR** | ⚠️ Tight (may timeout) | **Use optimized version** |

---

## 🚀 **Deployment Options**

### **Option 1: Deploy with Stub OCR** ⭐ **RECOMMENDED for Free Tier**

**Best for:** UI/UX demos, workflow demonstrations

**Pros:**
- ✅ Zero memory issues
- ✅ Instant processing
- ✅ Shows full pipeline
- ✅ Perfect for stakeholder demos

**Steps:**

```bash
cd /Users/jerrybony/Documents/GitHub/DocPipeline/essayflow

# 1. Ensure .gitignore is set up
cat >> .gitignore << 'EOF'
credentials/
*.json
.env
artifacts/*
outputs/*
.venv/
__pycache__/
*.pyc
EOF

# 2. Commit and push to GitHub
git add .
git commit -m "Deploy to Streamlit Cloud"
git push origin main
```

**Then:**
1. Go to https://share.streamlit.io/
2. Sign in with GitHub
3. Click "New app"
4. Repository: `DocPipeline`
5. Branch: `main`
6. Main file path: `essayflow/app.py`
7. Click "Deploy"!

**URL:** `https://<username>-essayflow.streamlit.app`

**Demo instructions:**
- Select "stub" from OCR dropdown
- Upload any file (content doesn't matter)
- Show the workflow, UI, and pipeline stages
- Explain that real OCR would extract actual text

---

### **Option 2: Deploy with Google Cloud Vision** 💰

**Best for:** Real OCR demos with credentials

**Pros:**
- ✅ Real OCR results
- ✅ Low memory usage
- ✅ Fast processing

**Cons:**
- ❌ Requires Google Cloud setup
- ❌ Costs money after free tier

**Steps:**

```bash
# 1. Get Google Cloud credentials
# (See GOOGLE_VISION_SETUP.md)

# 2. Push code to GitHub
git push origin main

# 3. Deploy on Streamlit Cloud (as above)

# 4. Add secrets in Streamlit Cloud dashboard:
# Settings → Secrets → Add:
```

**Secrets format (in Streamlit Cloud):**
```toml
# .streamlit/secrets.toml format
GOOGLE_CLOUD_VISION_CREDENTIALS_JSON = '''
{
  "type": "service_account",
  "project_id": "your-project",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...",
  "client_email": "...",
  "client_id": "...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "..."
}
'''
```

**Demo instructions:**
- Select "google" from OCR dropdown
- Upload real handwritten essay
- Show actual OCR extraction
- Demonstrate field extraction and validation

---

### **Option 3: Deploy with EasyOCR (Optimized)** 🔧

**Best for:** Real OCR without credentials (experimental on free tier)

**Pros:**
- ✅ Real OCR results
- ✅ No API keys needed
- ✅ Free forever

**Cons:**
- ⚠️ Tight memory on free tier (1GB)
- ⚠️ May timeout on first run (model download)
- ⚠️ Slower processing

**Steps:**

```bash
cd /Users/jerrybony/Documents/GitHub/DocPipeline/essayflow

# 1. Temporarily rename requirements files
mv requirements.txt requirements-local.txt
mv requirements-streamlit.txt requirements.txt

# 2. Make sure packages.txt exists (already created)
# This installs system dependencies

# 3. Commit and push
git add .
git commit -m "Optimize for Streamlit Cloud"
git push origin main

# 4. Deploy to Streamlit Cloud (as above)
```

**Settings in Streamlit Cloud:**
- Advanced settings → Python version: **3.11**
- Advanced settings → Click "Always rerun"

**Important notes:**
- ⚠️ **First user request will take 60-90 seconds** (model download)
- ⚠️ **May hit memory limit** and crash on free tier
- ⚠️ If it crashes, use stub or Google Vision instead
- ✅ If it works, subsequent requests are fast (~5-10 sec)

**Testing after deploy:**
```bash
# Monitor logs in Streamlit Cloud dashboard
# Look for:
# - "Downloading detection model..." ← EasyOCR working
# - "MemoryError" or "Killed" ← Out of memory, use stub instead
```

---

## 💡 **My Recommendation for Streamlit Cloud**

### **For FREE Tier Demos:**

**Use "stub" OCR** - Here's why:
- ✅ **Zero setup** - just deploy and go
- ✅ **Always works** - no memory issues
- ✅ **Instant results** - impressive for demos
- ✅ **Shows workflow** - stakeholders see the full pipeline
- ✅ **Explain easily** - "This uses simulated data, production would use real OCR"

**Demo script:**
> "Here's our EssayFlow system processing a handwritten essay. In this demo, I'm using simulated OCR output, but in production we'd use [Google Cloud Vision / EasyOCR] for real handwriting recognition. As you can see, the system extracts contact information, computes essay metrics, validates the data, and exports to CSV..."

### **If You Need Real OCR:**

**Option A - Google Cloud Vision:**
- Set up credentials once
- Add to Streamlit secrets
- Works reliably on free tier
- Costs ~$1.50 per 1,000 after free tier

**Option B - EasyOCR (risky on free tier):**
- Try it, but have backup plan
- May work with optimized requirements
- If it crashes, fall back to stub

**Option C - Upgrade Streamlit Cloud:**
- Streamlit Cloud Pro: $20/month
- 4GB RAM - EasyOCR works perfectly
- Worth it for serious demos

---

## 🎬 **Complete Deployment Walkthrough**

### **Step 1: Prepare Repository**

```bash
cd /Users/jerrybony/Documents/GitHub/DocPipeline/essayflow

# Create .gitignore if not exists
cat > .gitignore << 'EOF'
# Credentials (NEVER commit!)
credentials/
*.json
.env

# Python
.venv/
__pycache__/
*.pyc
*.pyo
*.pyd

# Artifacts (user data)
artifacts/*
outputs/*

# Keep directory structure
!artifacts/.gitkeep
!outputs/.gitkeep

# OS
.DS_Store
.DS_Store?
._*
Thumbs.db

# IDE
.vscode/
.idea/
*.swp
EOF

# Create .gitkeep files for empty directories
touch artifacts/.gitkeep
touch outputs/.gitkeep

# Commit everything
git add .
git commit -m "Prepare for Streamlit Cloud deployment"
git push origin main
```

### **Step 2: Deploy to Streamlit Cloud**

1. **Go to:** https://share.streamlit.io/
2. **Sign in** with GitHub
3. **Click:** "New app"
4. **Fill in:**
   - Repository: `yourusername/DocPipeline`
   - Branch: `main`
   - Main file path: `essayflow/app.py`
5. **Advanced settings:**
   - Python version: `3.11`
6. **Click:** "Deploy!"

### **Step 3: Wait for Build**

- First deployment: ~5-10 minutes
- Watch logs for progress
- Look for "Your app is now live!"

### **Step 4: Test Your App**

```
Your app URL: https://<username>-docpipeline.streamlit.app/
```

**Test checklist:**
- [ ] App loads successfully
- [ ] File uploader appears
- [ ] OCR dropdown shows options
- [ ] Upload a test file
- [ ] Select OCR provider
- [ ] Click "Run Processor"
- [ ] Results appear
- [ ] Artifacts section shows details
- [ ] CSV export works

### **Step 5: Share!**

```
Share URL: https://<username>-docpipeline.streamlit.app/

Share settings:
- Public (anyone with link)
- Private (requires login) - paid only
```

---

## 🐛 **Troubleshooting**

### **"Module not found: streamlit"**

**Fix:** Check `requirements.txt` in repo root
```bash
# Make sure requirements.txt exists at essayflow/requirements.txt
ls essayflow/requirements.txt
```

### **"Your app has exceeded the memory limit"**

**Cause:** EasyOCR too heavy for free tier

**Fix:** Switch to stub OCR
```python
# In UI, select "stub" instead of "easyocr"
```

Or upgrade to Streamlit Cloud Pro ($20/mo)

### **"App is taking too long to load"**

**Cause:** EasyOCR downloading models (first time)

**Wait:** Up to 2 minutes for first load

**Or:** Use stub OCR for instant loading

### **"Failed to import easyocr"**

**Fix 1:** Add to `requirements.txt`:
```txt
easyocr
torch
torchvision
opencv-python-headless
```

**Fix 2:** Use `requirements-streamlit.txt` (CPU-only version)

### **"Google Cloud Vision error"**

**Fix:** Add credentials to Streamlit secrets:
1. Dashboard → Settings → Secrets
2. Paste your JSON credentials
3. Restart app

---

## 📊 **Performance on Streamlit Cloud**

### **Expected Processing Times:**

| OCR Provider | Free Tier (1GB RAM) | First Run | Subsequent |
|--------------|---------------------|-----------|------------|
| **Stub** | ✅ Perfect | Instant | Instant |
| **Google** | ✅ Good | 1-2 sec | 1-2 sec |
| **EasyOCR** | ⚠️ May fail | 60-90 sec | 5-10 sec |

### **Memory Usage:**

| OCR Provider | Peak Memory | Free Tier Status |
|--------------|-------------|------------------|
| **Stub** | ~200MB | ✅ Plenty of room |
| **Google** | ~300MB | ✅ Works fine |
| **EasyOCR** | ~1.2GB | ⚠️ At limit |

---

## 💰 **Cost Comparison**

### **Streamlit Cloud:**
- **Free:** 1 private app, 1GB RAM, unlimited public apps
- **Pro:** $20/month, 4GB RAM, multiple private apps

### **EasyOCR on Streamlit Cloud:**
- Free tier: ⚠️ Risky (may crash)
- Pro tier: ✅ Works perfectly

### **Google Cloud Vision:**
- Free tier: 1,000 requests/month
- After: $1.50 per 1,000 requests

### **Recommendation:**
- **Demo/test:** Streamlit free + stub = $0
- **Real OCR occasionally:** Streamlit free + Google = ~$1-5/month
- **Real OCR frequently:** Streamlit Pro ($20/mo) + EasyOCR = $20/month

---

## ✅ **Quick Decision Matrix**

### **Choose Stub OCR if:**
- ✅ You're demoing the UI/workflow
- ✅ You want zero setup
- ✅ You don't need real OCR results
- ✅ You're on the free tier

### **Choose Google Cloud Vision if:**
- ✅ You need real OCR results
- ✅ You're okay setting up credentials
- ✅ You're fine with ~$1-2/month cost
- ✅ You're on the free tier

### **Choose EasyOCR if:**
- ✅ You need real OCR results
- ✅ You don't want to manage credentials
- ✅ You upgrade to Streamlit Pro ($20/mo)
- ⚠️ **Or** you're willing to risk crashes on free tier

---

## 🎯 **My Specific Recommendation for YOU**

Since you're using **Streamlit Cloud free tier** for demos:

### **Best Setup:**

```bash
# 1. Deploy as-is to Streamlit Cloud
git push

# 2. After deployment, in the UI:
#    - Default to "stub" OCR
#    - Explain it's for demo purposes
#    - Show the full pipeline workflow

# 3. For real demos (optional):
#    - Set up Google Cloud credentials
#    - Add to Streamlit secrets
#    - Switch to "google" OCR for impressive real results
```

### **Demo Script:**

> "Let me show you EssayFlow processing a handwritten essay. I'll use our test OCR for this demo [select 'stub'], but the system supports real OCR providers like Google Cloud Vision and EasyOCR. 
>
> Watch as it extracts the student's name, school, grade, computes word count, validates the data, and prepares it for CSV export. The entire pipeline runs automatically..."

**This approach:**
- ✅ Always works on free tier
- ✅ Shows the complete workflow
- ✅ Zero setup complexity
- ✅ Professional presentation

---

## 📚 **Additional Resources**

- **Streamlit Cloud Docs:** https://docs.streamlit.io/streamlit-community-cloud
- **Deployment Guide:** https://docs.streamlit.io/streamlit-community-cloud/deploy-your-app
- **Secrets Management:** https://docs.streamlit.io/streamlit-community-cloud/deploy-your-app/secrets-management

---

## 🚀 **Ready to Deploy?**

```bash
# Quick checklist:
cd /Users/jerrybony/Documents/GitHub/DocPipeline/essayflow

# 1. Verify .gitignore excludes credentials
cat .gitignore | grep credentials

# 2. Commit and push
git add .
git commit -m "Ready for Streamlit Cloud"
git push

# 3. Go to https://share.streamlit.io/
# 4. Deploy!
# 5. Share your URL: https://<username>-docpipeline.streamlit.app/
```

**Your app will be live in ~5-10 minutes!** 🎉

---

**Last Updated:** 2025-12-23  
**Status:** ✅ Ready for Streamlit Cloud deployment with multiple OCR options


