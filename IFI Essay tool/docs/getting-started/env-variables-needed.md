# Required Environment Variables

## Currently Missing (REQUIRED)

### 1. SUPABASE_URL
- **Where to find**: Supabase Dashboard > Settings > API > Project URL
- **Example**: `https://escbcdjlafzjxzqiephc.supabase.co`
- **Add to .env**: 
  ```bash
  SUPABASE_URL=https://escbcdjlafzjxzqiephc.supabase.co
  ```

### 2. SUPABASE_ANON_KEY
- **Where to find**: Supabase Dashboard > Settings > API > anon/public key
- **This is the public key** (safe to expose in frontend)
- **Add to .env**:
  ```bash
  SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
  ```

## Already Set (✅)

- ✅ `SUPABASE_SERVICE_ROLE_KEY` - Already in .env
- ✅ `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON` - Already in .env

## Optional (Recommended)

### 3. GROQ_API_KEY
- **Used for**: LLM extraction (free tier available)
- **Get from**: https://console.groq.com/
- **Optional**: App will work without it, but extraction may be limited

### 4. FLASK_SECRET_KEY
- **Used for**: Session encryption
- **Default**: Auto-generated if not set
- **Recommended**: Set a fixed value for production
- **Generate**: `python -c "import secrets; print(secrets.token_hex(32))"`

## Quick Setup Steps

1. **Go to Supabase Dashboard**:
   - https://supabase.com/dashboard/project/escbcdjlafzjxzqiephc/settings/api

2. **Copy the values**:
   - Project URL → `SUPABASE_URL`
   - anon public key → `SUPABASE_ANON_KEY`

3. **Add to your .env file**:
   ```bash
   SUPABASE_URL=https://escbcdjlafzjxzqiephc.supabase.co
   SUPABASE_ANON_KEY=your-anon-key-here
   ```

4. **Restart Docker containers**:
   ```bash
   docker-compose restart
   ```

## Complete .env Template

```bash
# Supabase Configuration
SUPABASE_URL=https://escbcdjlafzjxzqiephc.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here

# Google Cloud Vision
GOOGLE_CLOUD_VISION_CREDENTIALS_JSON={"type":"service_account",...}

# Optional
GROQ_API_KEY=your-groq-key-here
FLASK_SECRET_KEY=your-secret-key-here
```



