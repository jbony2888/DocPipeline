# 🚨 SECURITY INCIDENT: Exposed Service Account Credentials

## What Happened

Your Google Cloud service account credentials were exposed in a public GitHub repository:
- **File:** `COPY_THIS_EXACT_STRING.txt`
- **Commits:** `78044d8`, `da8ef48`
- **Service Account:** `essay-forms@youtube-ai-tool-478918.iam.gserviceaccount.com`
- **Key ID:** `1941d902d881dcaf66ff970127926db540894cb0`

**Google has DISABLED this key** - it no longer works.

## ⚠️ IMMEDIATE ACTIONS REQUIRED

### Step 1: Remove Credentials from Git History

The file is still in your git history even though it's deleted. You need to remove it completely:

#### Option A: Using git filter-branch (Recommended for small repos)

```bash
cd "/Users/jerrybony/Documents/GitHub/DocPipeline"

# Remove file from all commits
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch 'IFI Essay tool/COPY_THIS_EXACT_STRING.txt'" \
  --prune-empty --tag-name-filter cat -- --all

# Force push to GitHub (WARNING: This rewrites history)
git push origin --force --all
git push origin --force --tags
```

#### Option B: Using BFG Repo-Cleaner (Faster for large repos)

```bash
# Install BFG (if not installed)
# brew install bfg  # macOS
# or download from: https://rtyley.github.io/bfg-repo-cleaner/

cd "/Users/jerrybony/Documents/GitHub/DocPipeline"

# Remove the file
bfg --delete-files COPY_THIS_EXACT_STRING.txt

# Clean up
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# Force push
git push origin --force --all
```

### Step 2: Create New Service Account Key

1. **Go to Google Cloud Console:**
   https://console.cloud.google.com/iam-admin/serviceaccounts?project=youtube-ai-tool-478918

2. **Find the service account:**
   - Look for: `essay-forms@youtube-ai-tool-478918.iam.gserviceaccount.com`

3. **Create new key:**
   - Click on the service account
   - Go to "KEYS" tab
   - Click "ADD KEY" → "Create new key"
   - Choose "JSON" format
   - Download the new key file

4. **Delete the old key:**
   - In the KEYS tab, find the key with ID: `1941d902d881dcaf66ff970127926db540894cb0`
   - Click the trash icon to delete it

### Step 3: Update Environment Variables

#### For Local Development:

```bash
# Update your .env file
export GOOGLE_CLOUD_VISION_CREDENTIALS_JSON='<paste entire JSON content here>'
```

#### For Render (Production):

1. Go to Render Dashboard → Your Service → Environment
2. Find `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON`
3. Update with the new JSON content
4. Save and redeploy

#### For Docker:

Update your `docker-compose.yml` or `.env` file with the new credentials.

### Step 4: Verify Security

1. **Check .gitignore:**
   - ✅ `COPY_THIS_EXACT_STRING.txt` is already in `.gitignore` (line 53)
   - ✅ `*.credentials.json` is in `.gitignore` (line 55)

2. **Never commit credentials:**
   - ❌ Never commit `.json` files with credentials
   - ❌ Never commit files with actual keys
   - ✅ Only commit example/template files

3. **Use environment variables:**
   - ✅ Always use `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON` env var
   - ✅ Never hardcode credentials in code

## 🔒 Best Practices Going Forward

1. **Use Environment Variables:**
   - Store credentials in environment variables, not files
   - Use `.env` files locally (already in `.gitignore`)
   - Use platform secrets (Render, etc.) for production

2. **Use Secret Management:**
   - For production: Use Google Secret Manager
   - For CI/CD: Use GitHub Secrets or similar
   - Never commit secrets to git

3. **Regular Audits:**
   - Periodically check your git history for exposed secrets
   - Use tools like `git-secrets` or `truffleHog` to scan repos

4. **Rotate Keys Regularly:**
   - Rotate service account keys every 90 days
   - Delete old keys immediately after rotation

## ✅ Verification Checklist

- [ ] Removed credentials from git history
- [ ] Force pushed to GitHub (credentials no longer in repo)
- [ ] Created new service account key
- [ ] Deleted old disabled key from Google Cloud
- [ ] Updated `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON` in all environments
- [ ] Tested upload functionality with new credentials
- [ ] Verified `.gitignore` includes credential patterns
- [ ] Confirmed no other credential files are in the repo

## 🆘 If You Need Help

1. **Google Cloud Support:**
   - https://cloud.google.com/support
   - Mention the security incident and key rotation

2. **Check for Other Exposed Secrets:**
   ```bash
   # Search for potential credential files
   git log --all --full-history --source -- '*credentials*' '*key*' '*.json'
   ```

3. **Use GitHub's Secret Scanning:**
   - GitHub automatically scans for exposed secrets
   - Check your repository's security tab

## 📝 Notes

- The old key (`1941d902d881dcaf66ff970127926db540894cb0`) is **permanently disabled**
- You **must** create a new key to continue using Google Cloud Vision API
- Removing from git history is important to prevent anyone from finding the old key
- After force pushing, consider notifying collaborators about the history rewrite





