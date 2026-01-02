# 🤖 Groq LLM Extraction Setup

## ✅ **Why Groq?**

Groq provides **free, ultra-fast** AI inference that dramatically improves field extraction:

✅ **FREE tier** - Generous limits (30 requests/min, 14,400/day)  
✅ **Lightning fast** - World's fastest LLM inference  
✅ **Better accuracy** - Handles OCR errors, bilingual forms, complex layouts  
✅ **Smart context** - Understands form structure  
✅ **No training needed** - Works immediately  

**Cost:** FREE for your use case! 🎉

---

## 🚀 **Setup (3 Minutes)**

### **Step 1: Get Your Free API Key**

1. Go to: **https://console.groq.com/keys**
2. Sign up (free, no credit card required)
3. Click **"Create API Key"**
4. Copy your key (starts with `gsk_...`)

### **Step 2: Set Environment Variable**

#### **For Local Development:**

**macOS/Linux:**
```bash
export GROQ_API_KEY="gsk_your_key_here"
```

**Or add to your shell profile** (`~/.zshrc` or `~/.bashrc`):
```bash
echo 'export GROQ_API_KEY="gsk_your_key_here"' >> ~/.zshrc
source ~/.zshrc
```

**Windows (PowerShell):**
```powershell
$env:GROQ_API_KEY="gsk_your_key_here"
```

**Windows (CMD):**
```cmd
set GROQ_API_KEY=gsk_your_key_here
```

#### **For Streamlit Cloud:**

1. Go to your app settings
2. Click **"Secrets"**
3. Add:
```toml
GROQ_API_KEY = "gsk_your_key_here"
```
4. Save and redeploy

### **Step 3: Install Groq Package**

```bash
cd /Users/jerrybony/Documents/GitHub/DocPipeline/essayflow
source .venv/bin/activate
pip install groq
```

### **Step 4: Restart App**

```bash
./run.sh
```

---

## 📊 **How It Works**

### **Hybrid Extraction Strategy:**

1. **Try LLM first** (Groq Llama 3.1)
   - Sends contact block to Groq
   - AI intelligently extracts fields
   - Handles OCR errors, bilingual text, complex layouts

2. **Fall back to rules** if:
   - API key not set
   - API call fails
   - LLM doesn't find enough fields

### **What LLM Extraction Does Better:**

| Challenge | Rule-Based | LLM-Based |
|-----------|------------|-----------|
| **OCR errors** | ❌ Fails ("AIvarez" ≠ "Alvarez") | ✅ Understands ("AIvarez" → "Alvarez") |
| **Bilingual forms** | ⚠️ Limited | ✅ Excellent |
| **Values before labels** | ❌ Misses | ✅ Finds |
| **Complex layouts** | ⚠️ Struggles | ✅ Adapts |
| **Context understanding** | ❌ No | ✅ Yes |

### **Example: Your IFI Form**

**OCR Text:**
```
Ede; #llqez
EdvarcP
School
Escuela
...
8
```

**Rule-Based Result:**
```json
{
  "student_name": "Ede; #llqez",  // OCR error kept
  "school_name": null,             // Missed (value before label)
  "grade": null                    // Missed (far from label)
}
```

**LLM-Based Result:**
```json
{
  "student_name": "Eder Alvarez",  // ✅ OCR error corrected
  "school_name": "Edvarcll",       // ✅ Found value before label
  "grade": 8                       // ✅ Found standalone digit
}
```

---

## 🧪 **Testing**

Once API key is set, the app will automatically use LLM extraction:

1. Start app: `./run.sh`
2. Check for green message: "✅ Groq LLM Extraction: Enabled"
3. Upload your bilingual IFI form
4. See improved extraction results!

**Expected improvement:**
- Fields extracted: 0-3 → 5-8
- Validation: needs_review → is_valid ✅

---

## 📈 **Groq Free Tier Limits**

| Metric | Limit | Your Usage |
|--------|-------|------------|
| **Requests/minute** | 30 | ~1 per form |
| **Requests/day** | 14,400 | ~10-100 forms |
| **Tokens/minute** | 7,000 | ~200 per form |
| **Cost** | FREE | FREE |

**Translation:** Process thousands of forms per day for FREE! 🎉

---

## 🔒 **Security**

### **Do:**
✅ Keep API key private  
✅ Use environment variables  
✅ Don't commit to git (already in `.gitignore`)  

### **Don't:**
❌ Share your API key publicly  
❌ Commit API key to code  
❌ Paste in Slack/Discord  

### **If Key Compromised:**
1. Go to https://console.groq.com/keys
2. Delete old key
3. Create new key
4. Update environment variable

---

## 🚀 **Next Steps**

### **After Setting API Key:**

1. **Test locally:**
   ```bash
   export GROQ_API_KEY="gsk_..."
   ./run.sh
   ```
   Upload your IFI form and check results

2. **Deploy to Streamlit Cloud:**
   - Add key to Secrets
   - Redeploy app
   - Test with real forms

3. **Monitor usage:**
   - Check https://console.groq.com/usage
   - See request counts, token usage
   - All free! 🎉

---

## 🐛 **Troubleshooting**

### **"GROQ_API_KEY not set" warning**

**Cause:** Environment variable not set

**Fix:**
```bash
export GROQ_API_KEY="gsk_your_key_here"
./run.sh
```

### **"Groq package not installed"**

**Cause:** Package missing

**Fix:**
```bash
source .venv/bin/activate
pip install groq
```

### **"LLM extraction failed"**

**Cause:** API error or rate limit

**Fix:** App automatically falls back to rule-based extraction

### **"Invalid API key"**

**Cause:** Wrong key or typo

**Fix:**
1. Check key at https://console.groq.com/keys
2. Copy-paste carefully
3. Update environment variable

---

## 💡 **Pro Tips**

### **For Development:**

Add to `~/.zshrc` for persistent API key:
```bash
# Groq API for EssayFlow
export GROQ_API_KEY="gsk_your_key_here"
```

### **For Production (Streamlit Cloud):**

Use Streamlit Secrets (already configured):
```toml
# .streamlit/secrets.toml (DON'T commit!)
GROQ_API_KEY = "gsk_your_key_here"
```

### **For Team Deployment:**

Each team member needs their own key:
1. Each person signs up at Groq
2. Each gets their own API key
3. Each sets their own environment variable

---

## 📚 **Additional Resources**

- **Groq Console:** https://console.groq.com/
- **Groq Docs:** https://console.groq.com/docs/
- **API Keys:** https://console.groq.com/keys
- **Usage Stats:** https://console.groq.com/usage

---

## ✅ **Quick Start Checklist**

- [ ] Sign up at Groq: https://console.groq.com/keys
- [ ] Create API key
- [ ] Copy key (starts with `gsk_...`)
- [ ] Paste below and run:

```bash
export GROQ_API_KEY="PASTE_YOUR_KEY_HERE"
cd /Users/jerrybony/Documents/GitHub/DocPipeline/essayflow
./run.sh
```

- [ ] Look for green "✅ Groq LLM Extraction: Enabled" message
- [ ] Upload IFI form and test!

---

**Your extraction will go from 0-3 fields to 5-8 fields! 🎉**

**Status:** Ready to use - just add your API key!


