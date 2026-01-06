# Flask Migration Plan (If Needed)

## Current Issue
Streamlit has limitations with URL hash fragment handling (#access_token=...), making magic link authentication challenging.

## Flask Advantages
- ✅ Full control over routing and URL handling
- ✅ Easy OAuth/callback handling
- ✅ Better JavaScript integration
- ✅ More flexible authentication flows
- ✅ Better for production deployments

## Migration Approach

### Option 1: Full Flask Migration
Rewrite the entire app in Flask with:
- Flask + Jinja2 templates
- Bootstrap or Tailwind CSS for UI
- Same backend pipeline code (reusable)
- Better authentication flow

**Effort**: ~2-3 days of development

### Option 2: Hybrid Approach (Recommended)
Keep Streamlit for main app, add Flask microservice for auth:
- Flask app handles `/auth/callback` route
- Processes magic link tokens
- Sets session cookie
- Redirects back to Streamlit
- Streamlit reads session cookie

**Effort**: ~4-6 hours

### Option 3: Fix Streamlit (Current)
Continue debugging Streamlit implementation
- Use sessionStorage workaround
- Improve JavaScript execution
- Handle callbacks better

**Effort**: ~1-2 hours (if it works)

## Recommendation

**Try Option 3 first** (current approach). If magic link still doesn't work after this fix, **Option 2 (Hybrid)** is the best balance:
- Minimal code changes
- Keeps existing Streamlit UI
- Adds Flask just for auth callback
- Best of both worlds

## Next Steps

1. Test current Streamlit fix
2. If still not working → Implement Flask callback service
3. If that's too complex → Consider full Flask migration

