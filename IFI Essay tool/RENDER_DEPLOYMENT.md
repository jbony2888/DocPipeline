# Deploying IFI Essay Gateway on Render

## Prerequisites

1. **Render Account**: Sign up at https://render.com (free tier available)
2. **GitHub Repository**: Push your code to GitHub
3. **Google Cloud Vision Credentials**: JSON service account key
4. **Groq API Key**: From https://console.groq.com/keys

---

## Deployment Steps

### Step 1: Prepare Google Cloud Credentials

Since Render doesn't support file mounts, we need to convert your Google Cloud credentials to an environment variable.

**Option A: Use JSON String (Recommended)**

1. Open your Google Cloud service account JSON file
2. Copy the entire JSON content (all on one line)
3. You'll paste this into Render's environment variables

**Example:**
```json
{"type":"service_account","project_id":"your-project","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n","client_email":"...","client_id":"...","auth_uri":"...","token_uri":"...","auth_provider_x509_cert_url":"...","client_x509_cert_url":"..."}
```

**Option B: Convert to Single Line**

If your JSON has newlines, you can use this command:
```bash
cat your-credentials.json | jq -c
```

Or manually replace all newlines with `\n` and wrap in quotes.

---

### Step 2: Push Code to GitHub

```bash
cd "/Users/jerrybony/Documents/GitHub/DocPipeline/IFI Essay tool"
git init  # If not already a git repo
git add .
git commit -m "Initial commit - ready for Render deployment"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```

---

### Step 3: Create Web Service on Render

1. **Go to Render Dashboard**: https://dashboard.render.com
2. **Click "New +"** → **"Web Service"**
3. **Connect Repository**: Select your GitHub repository
4. **Configure Service**:
   - **Name**: `ifi-essay-gateway`
   - **Region**: `Oregon` (or closest to you)
   - **Branch**: `main`
   - **Root Directory**: `IFI Essay tool` (or `.` if repo root is the tool directory)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements-docker.txt`
   - **Start Command**: `streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true`

---

### Step 4: Set Environment Variables

**Important:** Render uses the dashboard for environment variables, NOT the YAML file directly. The `render.yaml` file is for Infrastructure as Code, but secrets should be set in the dashboard.

#### Method 1: Use Helper Script (Easiest)

```bash
# Prepare your Google credentials for Render
python scripts/prepare_render_env.py /path/to/your/google-credentials.json
```

This will:
- Format your JSON correctly (single-line)
- Print instructions
- Save formatted JSON to `render_google_creds.txt` for easy copy/paste

#### Method 2: Manual Setup in Render Dashboard

1. **Go to Render Dashboard**: https://dashboard.render.com
2. **Select your service**: `ifi-essay-gateway`
3. **Click**: "Environment" tab
4. **Click**: "Add Environment Variable" for each:

**Variable 1:**
   - **Key**: `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON`
   - **Value**: Your entire Google Cloud JSON as single-line string
   - **How to format**: 
     ```bash
     # Option A: Use the helper script
     python scripts/prepare_render_env.py your-credentials.json
     
     # Option B: Manual (Mac/Linux)
     cat your-credentials.json | jq -c
     
     # Option C: Manual (convert multi-line to single-line)
     # Remove all newlines, keep \n in private_key values
     ```

**Variable 2:**
   - **Key**: `GROQ_API_KEY`
   - **Value**: `gsk_your_actual_groq_key_here`

#### Optional Variables (Default values will be used if not set):

- `STREAMLIT_SERVER_PORT` = `$PORT` (Render provides this)
- `STREAMLIT_SERVER_ADDRESS` = `0.0.0.0`
- `STREAMLIT_SERVER_HEADLESS` = `true`

---

### Step 5: Deploy

1. Click **"Create Web Service"**
2. Render will start building and deploying
3. Monitor the build logs
4. Once deployed, you'll get a URL like: `https://ifi-essay-gateway.onrender.com`

---

## Using render.yaml (Alternative Method)

If you prefer Infrastructure as Code:

1. Ensure `render.yaml` is in your repository root
2. In Render dashboard, select **"Apply render.yaml"**
3. Render will read the configuration from the file
4. You still need to set environment variables manually in the dashboard

---

## Important Notes

### Storage Limitations

**Free Tier:**
- Ephemeral filesystem (data may be lost on restarts)
- Limited disk space (~1GB)
- Files are lost if the service is idle and spins down

**Solutions:**
1. **Use External Storage**: Store artifacts in S3, Google Cloud Storage, or similar
2. **Database**: Consider using Render PostgreSQL (free tier available)
3. **Persistent Disk**: Upgrade to paid plan for persistent disk storage

### Database Persistence

Currently using SQLite in local filesystem. Options:

1. **Keep SQLite** (data may be lost on restarts/spin-downs)
2. **Use Render PostgreSQL** (free tier available):
   ```python
   # Update database.py to use PostgreSQL connection string
   DATABASE_URL = os.getenv("DATABASE_URL")  # Render provides this
   ```
3. **Use External Database**: AWS RDS, Google Cloud SQL, etc.

### Idle Spin-Down

**Free tier services spin down after 15 minutes of inactivity**

- First request after spin-down takes ~30 seconds
- Consider upgrading to **Starter Plan** ($7/month) to avoid spin-down

---

## Troubleshooting

### Build Fails

1. **Check Build Logs**: Look for specific error messages
2. **Verify requirements-docker.txt**: All dependencies listed?
3. **Python Version**: Ensure it matches your local setup (3.11)

### App Won't Start

1. **Check Start Command**: Must use `$PORT` variable
2. **Check Logs**: Look for Python errors
3. **Verify Environment Variables**: All required vars set?

### Google Vision Not Working

1. **Check Credentials Format**: Must be valid JSON string
2. **Verify Service Account**: Has Vision API enabled?
3. **Check Billing**: Google Cloud billing enabled?

### Database Errors

1. **Create data directory**: Add to build command if needed
2. **Check Permissions**: Ensure app can write to directories
3. **Consider PostgreSQL**: More reliable on Render

---

## Cost Estimation

### Free Tier
- $0/month
- 512MB RAM, 0.5 CPU
- 15-minute idle spin-down
- Ephemeral disk

### Starter Plan (Recommended)
- $7/month
- 512MB RAM, 0.5 CPU
- No spin-down
- Persistent disk
- Better for production use

---

## Recommended Setup for Production

1. **Use Starter Plan** ($7/month) - No spin-down, persistent storage
2. **Use Render PostgreSQL** (Free tier) - Database persistence
3. **Add External Storage** (S3/GCS) - For artifacts (optional)
4. **Set up Monitoring** - Render provides basic monitoring

---

## Security Best Practices

1. **Never commit credentials** to Git
2. **Use environment variables** for all secrets
3. **Enable Render's SSL** (automatic on custom domains)
4. **Set up secret rotation** for API keys
5. **Use least-privilege IAM** for Google Cloud service account

---

## Next Steps After Deployment

1. **Test the deployment**: Upload a test submission
2. **Set up custom domain** (optional)
3. **Configure monitoring/alerts** (optional)
4. **Set up backups** for database (if using PostgreSQL)
5. **Document the deployment** for your team

---

## Support

- **Render Docs**: https://render.com/docs
- **Render Support**: support@render.com
- **Streamlit on Render**: https://render.com/docs/deploy-streamlit

---

**Last Updated:** December 2024

