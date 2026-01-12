# Security Guidelines

## Environment Variables

This project uses environment variables to store sensitive credentials. **Never commit actual secrets to Git.**

### Setup

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and fill in your actual values:
   ```bash
   # Supabase Configuration
   SUPABASE_URL=https://your-project-id.supabase.co
   SUPABASE_ANON_KEY=your-supabase-anon-key-here
   SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key-here
   
   # Flask Configuration
   FLASK_SECRET_KEY=generate-a-secure-random-key-here
   
   # API Keys
   GROQ_API_KEY=your-groq-api-key-here
   ```

3. The `.env` file is automatically ignored by Git (see `.gitignore`)

### Generating Secure Keys

**Flask Secret Key:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Where to Find Your Keys

- **Supabase Keys**: Go to [Supabase Dashboard](https://supabase.com/dashboard) → Your Project → Settings → API
  - `SUPABASE_URL`: Your project URL
  - `SUPABASE_ANON_KEY`: The "anon" public key
  - `SUPABASE_SERVICE_ROLE_KEY`: The "service_role" secret key (⚠️ Keep this secret!)

- **Groq API Key**: Get it from [Groq Console](https://console.groq.com/keys)

### Files That Should NOT Contain Secrets

The following files have been sanitized and should only contain placeholders:
- `START_FLASK_APP.sh`
- `START_FLASK_AUTH.sh`
- `docker-compose.yml`
- `test_auth_flow.py`
- All documentation files (`.md` files)

### Files That Are Git-Ignored

These files are automatically excluded from Git:
- `.env`
- `.env.local`
- `.env.production`
- `credentials/`
- `*service-account*.json`
- `*.pem`
- `*.key`

### For Production Deployment

When deploying to Render or other platforms:
1. Set environment variables in your platform's dashboard
2. **Never** hardcode secrets in code or configuration files
3. Use platform-specific secret management features when available

### Reporting Security Issues

If you discover a security vulnerability, please report it responsibly.



