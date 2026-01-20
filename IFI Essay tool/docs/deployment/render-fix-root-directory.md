# Fix Render "Dockerfile not found" Error

## Problem

Render is looking for `Dockerfile` in the repository root, but your files are in the `IFI Essay tool/` subdirectory.

**Error:**
```
error: failed to solve: failed to read dockerfile: open Dockerfile: no such file or directory
```

## Solution: Set Root Directory in Render

### Option 1: Set Root Directory in Render Dashboard (Recommended)

1. **Go to Render Dashboard**: https://dashboard.render.com
2. **Select your service**: `ifi-essay-gateway`
3. **Click**: "Settings" tab (left sidebar)
4. **Scroll down** to "Build & Deploy" section
5. **Find**: "Root Directory" field
6. **Set to**: `IFI Essay tool` (or `IFI Essay tool/` with trailing slash)
7. **Click**: "Save Changes"
8. **Redeploy**: Click "Manual Deploy" → "Clear build cache & deploy"

### Option 2: Update render.yaml (If using Infrastructure as Code)

If you're using `render.yaml`, you need to ensure it's in the repo root OR update the service configuration in the dashboard.

---

## Alternative: Move Files to Repo Root (Not Recommended)

If you prefer, you could move everything to the repo root, but this changes your repository structure.

---

## Quick Fix Steps

1. ✅ Go to Render Dashboard
2. ✅ Click your service → "Settings"
3. ✅ Set "Root Directory" = `IFI Essay tool`
4. ✅ Save
5. ✅ Redeploy

That's it! Render will now look for `Dockerfile` in the `IFI Essay tool/` directory.

---

## Verify Your Repository Structure

Your repo structure should be:
```
DocPipeline/
├── IFI Essay tool/
│   ├── Dockerfile          ← Render will find this
│   ├── render.yaml
│   ├── app.py
│   └── ...
└── (other files)
```

With "Root Directory" set to `IFI Essay tool`, Render will:
- Look for `Dockerfile` in `IFI Essay tool/`
- Run build commands from `IFI Essay tool/`
- Use `requirements-docker.txt` from `IFI Essay tool/`

---

**Last Updated:** December 2024





