# EssayFlow Deployment Guide

## 🎯 **Quick Answer: Yes, You Can Demo This!**

EssayFlow can be deployed to various hosting platforms for testing and demos. Here are your options:

---

## 🚀 **Deployment Options**

### **Quick Comparison**

| Platform | Setup Time | Cost | Best For | EasyOCR Support |
|----------|------------|------|----------|-----------------|
| **Streamlit Cloud** | 5 min | FREE | Quick demos | ⚠️ Limited (RAM) |
| **Docker (Local)** | 10 min | FREE | Development | ✅ Full support |
| **Railway** | 10 min | FREE tier | Easy deploy | ✅ Full support |
| **Render** | 15 min | FREE tier | Production | ✅ Full support |
| **AWS/GCP/Azure** | 30+ min | Pay-as-go | Enterprise | ✅ Full support |

---

## 1️⃣ **Streamlit Cloud** ⭐ **Easiest Demo**

### **Perfect For:**
- Quick public demo
- Sharing with stakeholders
- Testing UI/UX
- No server management

### **Setup Steps:**

**Step 1: Prepare Repository**
```bash
cd /Users/jerrybony/Documents/GitHub/DocPipeline/essayflow

# Add packages_cpu.txt for Streamlit Cloud (CPU-only PyTorch)
cat > packages_cpu.txt << EOF
torch==2.1.0+cpu
torchvision==0.16.0+cpu
EOF

# Update .gitignore
cat >> .gitignore << EOF
credentials/
*.json
.env
artifacts/*
outputs/*
!artifacts/.gitkeep
!outputs/.gitkeep
EOF

# Commit and push
git add .
git commit -m "Prepare for Streamlit Cloud deployment"
git push origin main
```

**Step 2: Deploy**
1. Go to https://share.streamlit.io/
2. Sign in with GitHub
3. Click "New app"
4. Select your repository: `DocPipeline`
5. Branch: `main`
6. Main file: `essayflow/app.py`
7. Click "Deploy"!

**Step 3: Configure (if needed)**
- Advanced settings → Python version: 3.11
- Secrets (if using Google OCR):
  ```toml
  GOOGLE_CLOUD_VISION_CREDENTIALS_JSON = '{"type":"service_account",...}'
  ```

### **Important Notes:**
- ⚠️ **Streamlit Cloud has 1GB RAM limit** - EasyOCR may struggle
- 💡 **Recommendation:** Use "stub" OCR for Streamlit Cloud demos
- 🔒 **Security:** Your app will be public unless you use sharing settings
- ⏱️ **Cold starts:** App sleeps after 30 min inactivity (takes ~30 sec to wake)

### **Testing URL:**
After deployment: `https://<your-username>-essayflow.streamlit.app`

---

## 2️⃣ **Docker (Local Testing)** 💻 **Best for Development**

### **Perfect For:**
- Local demos
- Development testing
- Full control
- Network demos (local WiFi)

### **Setup Steps:**

**Step 1: Build Docker Image**
```bash
cd /Users/jerrybony/Documents/GitHub/DocPipeline/essayflow

# Build the image
docker build -t essayflow:latest .

# Or use docker-compose
docker-compose up --build
```

**Step 2: Run Container**
```bash
# Simple run
docker run -p 8501:8501 essayflow:latest

# With volume mounts (persist data)
docker run -p 8501:8501 \
  -v $(pwd)/artifacts:/app/artifacts \
  -v $(pwd)/outputs:/app/outputs \
  essayflow:latest

# Or use docker-compose (recommended)
docker-compose up
```

**Step 3: Access**
- Local: http://localhost:8501
- Network: http://YOUR_IP:8501

### **First Run:**
- EasyOCR models download (~100MB, 30-60 seconds)
- Models cached in container for future runs
- If container is recreated, models re-download

### **Making Models Persistent:**
```yaml
# Add to docker-compose.yml:
volumes:
  - ./artifacts:/app/artifacts
  - ./outputs:/app/outputs
  - ~/.EasyOCR:/root/.EasyOCR  # Persist EasyOCR models
```

---

## 3️⃣ **Railway** 🚂 **Easy Cloud Deploy**

### **Perfect For:**
- Production demos
- Permanent test environment
- Easy CI/CD

### **Setup Steps:**

**Step 1: Install Railway CLI**
```bash
npm install -g @railway/cli
# Or use web interface
```

**Step 2: Deploy**
```bash
cd /Users/jerrybony/Documents/GitHub/DocPipeline/essayflow

# Login
railway login

# Initialize
railway init

# Deploy
railway up
```

**Step 3: Configure**
```bash
# Set port
railway variables set PORT=8501

# Optional: Add Google Cloud credentials
railway variables set GOOGLE_CLOUD_VISION_CREDENTIALS_JSON='{"type":...}'
```

### **Pricing:**
- **Free tier:** 500 hours/month, $5 credit
- **Enough for:** Continuous testing/demos
- **Paid:** $5/month for starter plan

### **URL:**
Railway provides: `https://essayflow-production-xxxx.up.railway.app`

---

## 4️⃣ **Render** 🎨 **Good Free Tier**

### **Perfect For:**
- Long-term free hosting
- Production-like environment
- Automatic deploys from GitHub

### **Setup Steps:**

**Step 1: Create `render.yaml`**
```yaml
# essayflow/render.yaml
services:
  - type: web
    name: essayflow
    env: docker
    plan: free
    healthCheckPath: /_stcore/health
    envVars:
      - key: PORT
        value: 8501
```

**Step 2: Deploy**
1. Go to https://render.com
2. Sign up with GitHub
3. New → Web Service
4. Connect repository
5. Select "Docker"
6. Deploy!

### **Pricing:**
- **Free tier:** Available
- **Limitations:** Spins down after 15 min inactivity
- **Paid:** $7/month for always-on

### **URL:**
Render provides: `https://essayflow.onrender.com`

---

## 5️⃣ **Cloud VMs** ☁️ **Full Control**

### **AWS EC2 / GCP Compute / Azure VM**

**Perfect For:**
- Production deployment
- High traffic
- Full customization

### **Quick Setup (Ubuntu VM):**

```bash
# SSH into your VM
ssh user@your-vm-ip

# Install Docker
curl -fsSL https://get.docker.com | sh

# Clone repository
git clone https://github.com/yourusername/DocPipeline.git
cd DocPipeline/essayflow

# Run with docker-compose
docker-compose up -d

# Access at http://your-vm-ip:8501
```

### **Security:**
```bash
# Use nginx reverse proxy for HTTPS
sudo apt install nginx certbot python3-certbot-nginx

# Configure nginx
sudo nano /etc/nginx/sites-available/essayflow
```

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

---

## 🔒 **Security Considerations**

### **For Public Demos:**

1. **Remove Sensitive Features:**
```python
# In app.py, add authentication
import streamlit_authenticator as stauth

# Simple password protection
password = st.text_input("Password", type="password")
if password != "your_demo_password":
    st.stop()
```

2. **Limit File Uploads:**
```python
# In app.py
uploaded_file = st.file_uploader(
    "Choose an image file",
    type=["png", "jpg", "jpeg", "pdf"],
    help="Max 10MB"
)
if uploaded_file and uploaded_file.size > 10_000_000:
    st.error("File too large! Max 10MB.")
    st.stop()
```

3. **Rate Limiting:**
```python
# Use streamlit-session-state to track uploads
if 'upload_count' not in st.session_state:
    st.session_state.upload_count = 0

if st.session_state.upload_count >= 10:
    st.error("Demo limit reached (10 uploads). Refresh to continue.")
    st.stop()
```

### **Environment Variables:**
```bash
# Never commit credentials!
# Set via platform's secret management:

# Streamlit Cloud: Secrets management
# Railway: railway variables set KEY=value
# Render: Environment variables in dashboard
# Docker: .env file (in .gitignore)
```

---

## 📊 **Resource Requirements**

### **Minimum Specs:**

| Provider | RAM | CPU | Disk | Notes |
|----------|-----|-----|------|-------|
| **EasyOCR** | 2GB | 1 core | 1GB | Models ~100MB |
| **Google Vision** | 512MB | 1 core | 100MB | Cloud-based OCR |
| **Stub** | 256MB | 1 core | 50MB | No real OCR |

### **Recommendations:**

**For EasyOCR:**
- ✅ **Minimum:** 2GB RAM, 1 CPU
- 🚀 **Recommended:** 4GB RAM, 2 CPU
- ⚡ **Optimal:** GPU instance (faster processing)

**For Demo (Stub OCR):**
- ✅ **Minimum:** 512MB RAM, 1 CPU
- Perfect for Streamlit Cloud free tier!

---

## 🎯 **Recommended Setup by Use Case**

### **Quick Demo (15 minutes)**
→ **Streamlit Cloud** with "stub" OCR
- No setup, just push to GitHub
- Free forever
- Public URL to share

### **Client Presentation (1 hour)**
→ **Docker on your laptop**
- Full EasyOCR support
- Offline capable
- Professional setup

### **Internal Testing (ongoing)**
→ **Railway or Render**
- Permanent URL
- Free tier
- Real OCR capability

### **Production Deployment**
→ **Cloud VM with Docker**
- Full control
- Scalable
- Secure

---

## 🧪 **Testing Your Deployment**

### **Checklist:**

```bash
# 1. Health check
curl https://your-app-url/_stcore/health

# 2. Upload test
# - Go to URL
# - Upload sample image
# - Select OCR provider
# - Click "Run Processor"
# - Verify results appear

# 3. Artifact check
# - Check artifacts/ directory created
# - Verify metadata.json exists
# - Check all pipeline artifacts present

# 4. CSV export test
# - Process a submission
# - Click "Write to CSV"
# - Check outputs/ directory

# 5. Performance test
# - Time the processing
# - Monitor memory usage
# - Check for errors in logs
```

---

## 📝 **Deployment Checklist**

### **Before Deploying:**

- [ ] Remove or gitignore credentials
- [ ] Test locally with `./run.sh`
- [ ] Test Docker build: `docker build -t essayflow .`
- [ ] Verify all dependencies in requirements.txt
- [ ] Choose OCR provider (stub for low-resource demos)
- [ ] Set resource limits appropriately
- [ ] Add health check endpoint
- [ ] Configure environment variables
- [ ] Set up monitoring (optional)

### **After Deploying:**

- [ ] Test the deployed URL
- [ ] Upload sample file
- [ ] Verify OCR works
- [ ] Check artifact creation
- [ ] Test CSV export
- [ ] Monitor resource usage
- [ ] Share URL with team
- [ ] Document access details

---

## 🚀 **Quick Start: Docker Demo**

**Fastest way to demo locally or on a server:**

```bash
cd /Users/jerrybony/Documents/GitHub/DocPipeline/essayflow

# Build and run
docker-compose up --build

# Access at http://localhost:8501

# Share on local network
# Find your IP: ifconfig | grep inet
# Share: http://YOUR_IP:8501
```

**For presentation:**
- Put laptop on projector
- Or share screen via Zoom/Teams
- Or deploy to Streamlit Cloud day-of

---

## 💡 **Pro Tips**

### **For Demos:**
1. **Pre-process test images** - Have sample PDFs ready
2. **Use stub OCR** - Instant results, no waiting
3. **Prepare backup** - Screen recording if live demo fails
4. **Test WiFi** - Ensure stable connection if cloud-hosted

### **For Testing:**
1. **Use EasyOCR** - Real OCR without credentials
2. **Docker volumes** - Persist artifacts between restarts
3. **Resource monitoring** - Watch RAM/CPU usage
4. **Logs** - Check for errors: `docker logs essayflow`

### **For Production:**
1. **Use Google Vision** - Best accuracy
2. **Add authentication** - Protect from abuse
3. **Rate limiting** - Prevent resource exhaustion
4. **Monitoring** - Uptime checks, error tracking
5. **Backups** - Regular CSV exports

---

## 📚 **Additional Resources**

- **Streamlit Cloud Docs:** https://docs.streamlit.io/streamlit-community-cloud
- **Docker Docs:** https://docs.docker.com/
- **Railway Docs:** https://docs.railway.app/
- **Render Docs:** https://render.com/docs

---

## ✅ **Quick Decision Guide**

**I need to demo in...**

**5 minutes:**
→ Run locally: `./run.sh` and share screen

**15 minutes:**
→ Streamlit Cloud (stub OCR)

**1 hour:**
→ Docker on your machine, demo on local network

**1 day:**
→ Railway/Render (EasyOCR, permanent URL)

**Production:**
→ Cloud VM with Docker + nginx

---

**Last Updated:** 2025-12-23  
**Status:** ✅ Ready for deployment!


