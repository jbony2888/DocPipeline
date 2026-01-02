# Quick Deploy to Render - 5 Minutes

## Prerequisites Checklist
- [ ] Render account (free at https://render.com)
- [ ] Code pushed to GitHub
- [ ] Google Cloud Vision credentials JSON file
- [ ] Groq API key

---

## Step 1: Prepare Credentials

### Google Cloud Credentials
Convert your JSON file to a single-line string:

```bash
# On Mac/Linux:
cat /path/to/your-credentials.json | jq -c

# Or manually: Copy entire JSON, remove all newlines, ensure it's on one line
```

**Example format:**
```
{"type":"service_account","project_id":"your-project",...}
```

---

## Step 2: Deploy on Render

1. **Go to**: https://dashboard.render.com
2. **Click**: "New +" → "Web Service"
3. **Connect**: Your GitHub repository
4. **Configure**:
   - **Name**: `ifi-essay-gateway`
   - **Root Directory**: `IFI Essay tool` (if repo root is DocPipeline) or `.` (if repo root is the tool)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements-docker.txt && mkdir -p artifacts outputs data`
   - **Start Command**: `streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true`

---

## Step 3: Set Environment Variables

Click **"Environment"** tab and add:

1. **GOOGLE_CLOUD_VISION_CREDENTIALS_JSON**
   - Paste your entire JSON (single line)
   - Value: `{"type":"service_account",...}`

2. **GROQ_API_KEY**
   - Your Groq API key
   - Value: `gsk_...`

---

## Step 4: Deploy

Click **"Create Web Service"** and wait ~2-3 minutes.

Your app will be live at: `https://ifi-essay-gateway.onrender.com`

---

## Important Notes

### Free Tier Limitations
- ✅ **FREE** but spins down after 15 minutes of inactivity
- ⚠️ First request after spin-down takes ~30 seconds
- 💡 **Recommendation**: Upgrade to Starter ($7/month) for production

### Storage
- Files are **ephemeral** on free tier (lost on restart/spin-down)
- For production, consider:
  - Upgrade to Starter plan (persistent disk)
  - Use external storage (S3/GCS) for artifacts
  - Use Render PostgreSQL for database

---

## Troubleshooting

**Build fails?** Check logs, verify `requirements-docker.txt` exists.

**App won't start?** Ensure start command uses `$PORT`.

**Credentials error?** Verify JSON is valid and on one line.

**Need help?** See full guide: `RENDER_DEPLOYMENT.md`

