# Deploy to Streamlit Cloud (Recommended)

**The easiest way to deploy Streamlit apps - Official hosting by Streamlit**

---

## Why Streamlit Cloud?

✅ **Free forever** (for public repos)  
✅ **One-click deploy** from GitHub  
✅ **Official support** - best compatibility  
✅ **Automatic HTTPS**  
✅ **No credit card required**

---

## Prerequisites

- [ ] GitHub account
- [ ] Code pushed to GitHub (public or private repo)
- [ ] Google Cloud Vision credentials JSON
- [ ] Groq API key

---

## Step 1: Push Code to GitHub

```bash
cd "/Users/jerrybony/Documents/GitHub/DocPipeline/IFI Essay tool"

# Initialize git if needed
git init

# Add files (exclude large/private files)
git add app.py pipeline/ requirements*.txt *.md
git add .gitignore

# Commit
git commit -m "Ready for Streamlit Cloud deployment"

# Add remote (replace with your repo URL)
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git branch -M main
git push -u origin main
```

**Important:** Don't commit:
- `credentials.json` files
- `data/` directory (if contains sensitive data)
- Large `artifacts/` directories

---

## Step 2: Deploy on Streamlit Cloud

1. **Go to**: https://share.streamlit.io
2. **Sign in** with your GitHub account
3. **Click**: "New app" button
4. **Configure**:
   - **Repository**: Select your GitHub repo
   - **Branch**: `main` (or your branch)
   - **Main file path**: `app.py`
   - **App URL**: Choose your subdomain (e.g., `ifi-essay-gateway`)
5. **Click**: "Deploy"

Streamlit Cloud will automatically:
- Install dependencies from `requirements.txt` or `requirements-docker.txt`
- Deploy your app
- Provide HTTPS URL

---

## Step 3: Configure Environment Variables

1. **Go to**: Your app's settings in Streamlit Cloud dashboard
2. **Click**: "Settings" → "Secrets"
3. **Add secrets** (click "New secret" for each):

### Required Secrets:

**GOOGLE_CLOUD_VISION_CREDENTIALS_JSON**
```
Value: Paste your entire Google Cloud service account JSON (as single-line string)
Example: {"type":"service_account","project_id":"...","private_key":"..."}
```

**GROQ_API_KEY**
```
Value: Your Groq API key
Example: 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
```

### Optional Secrets:

**STREAMLIT_SERVER_PORT** (usually not needed - auto-configured)  
**STREAMLIT_SERVER_ADDRESS** (usually not needed - auto-configured)

---

## Step 4: Verify Deployment

1. **Wait** for deployment to complete (~2-3 minutes)
2. **Open** your app URL: `https://your-app-name.streamlit.app`
3. **Check** the app loads correctly
4. **Test** by uploading a test submission

---

## File Structure for Streamlit Cloud

Your repo should have:
```
IFI Essay tool/
├── app.py                    # Main Streamlit app
├── pipeline/                 # Your pipeline modules
│   ├── __init__.py
│   ├── ocr.py
│   ├── extract_ifi.py
│   └── ...
├── requirements-docker.txt   # Dependencies (or requirements.txt)
└── .streamlit/              # Optional: Streamlit config
    └── config.toml
```

**Don't include:**
- `artifacts/` (large files)
- `data/` (contains database - not needed, will recreate)
- `credentials.json` (use secrets instead)
- `.venv/` (virtual environment)

---

## Configuration Options

### Create `.streamlit/config.toml` (Optional)

```toml
[server]
headless = true
port = 8501
address = "0.0.0.0"

[theme]
primaryColor = "#FF6B6B"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"
textColor = "#262730"
```

### Create `.streamlit/secrets.toml` (Local Testing Only)

For local testing, you can create this file (but **don't commit it**):

```toml
GOOGLE_CLOUD_VISION_CREDENTIALS_JSON = '{"type":"service_account",...}'
GROQ_API_KEY = "gsk_..."
```

**Important:** Add to `.gitignore`:
```
.streamlit/secrets.toml
```

---

## Troubleshooting

### Build Fails

**Problem:** App won't deploy  
**Solution:**
1. Check build logs in Streamlit Cloud dashboard
2. Verify `requirements-docker.txt` exists and is correct
3. Ensure all dependencies are listed

### Import Errors

**Problem:** `ModuleNotFoundError`  
**Solution:**
1. Check all Python files are committed
2. Verify `pipeline/` directory is included
3. Ensure `__init__.py` files exist in package directories

### Credentials Not Working

**Problem:** Google Vision or Groq not working  
**Solution:**
1. Check secrets are set correctly in Streamlit Cloud
2. Verify JSON is valid (single-line, no newlines)
3. Test credentials locally first

### App Crashes

**Problem:** App loads but crashes  
**Solution:**
1. Check logs in Streamlit Cloud dashboard
2. Look for Python errors
3. Test locally first: `streamlit run app.py`

---

## Free Tier Limitations

### Public Repos (Free)
- ✅ 3 apps per account
- ✅ Unlimited deploys
- ✅ Automatic HTTPS
- ⚠️ App sleeps after inactivity (wakes automatically on request)

### Private Repos
- 💰 Requires **Team plan** ($20/month)
- ✅ Unlimited apps
- ✅ Private repos
- ✅ Priority support

---

## Updating Your App

**Automatic Updates:**
- Streamlit Cloud watches your GitHub repo
- When you push changes, it auto-redeploys

**Manual Redeploy:**
1. Go to app dashboard
2. Click "Manage app"
3. Click "Reboot app" or "Redeploy"

---

## Custom Domain (Optional)

1. Go to app settings
2. Click "Settings" → "General"
3. Enter your custom domain
4. Follow DNS instructions

---

## Cost Comparison

| Plan | Cost | Features |
|------|------|----------|
| **Free** | $0/month | Public repos, 3 apps, auto-sleep |
| **Team** | $20/month | Private repos, unlimited apps, priority support |

---

## Comparison with Other Providers

| Feature | Streamlit Cloud | Render | Railway |
|---------|----------------|--------|---------|
| Free Tier | ✅ Yes | ⚠️ Spins down | ✅ $5 credit |
| Setup | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| Official Support | ✅ Yes | ❌ No | ❌ No |
| Private Repos | 💰 Paid | ✅ Free | ✅ Free |

---

## Next Steps

1. ✅ Deploy to Streamlit Cloud (follow steps above)
2. ✅ Test your deployment
3. ✅ Share URL with team
4. 💡 Consider custom domain
5. 💡 Set up monitoring/alerts

---

## Support

- **Streamlit Cloud Docs**: https://docs.streamlit.io/streamlit-cloud
- **Streamlit Community**: https://discuss.streamlit.io
- **Streamlit Support**: support@streamlit.io

---

**Last Updated:** December 2024

