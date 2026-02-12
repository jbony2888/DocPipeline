#!/bin/bash
# Quick setup script for local DBF testing

echo "🔧 Setting up local DBF testing environment"
echo "=========================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file from .env.example..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ Created .env file"
        echo ""
        echo "⚠️  IMPORTANT: Edit .env file and add your Supabase credentials:"
        echo "   - SUPABASE_URL"
        echo "   - SUPABASE_ANON_KEY"
        echo "   - SUPABASE_SERVICE_ROLE_KEY"
        echo ""
    else
        echo "⚠️  No .env.example found. Creating basic .env template..."
        cat > .env << EOF
# Supabase Configuration
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here

# Flask Configuration
FLASK_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')
FLASK_PORT=5000

# API Keys (optional for testing)
# GROQ_API_KEY=your-groq-key
# OPENAI_API_KEY=your-openai-key
# GOOGLE_CLOUD_VISION_CREDENTIALS_JSON='{"type":"service_account",...}'
EOF
        echo "✅ Created .env file"
        echo ""
        echo "⚠️  Edit .env and add your Supabase credentials!"
    fi
else
    echo "✅ .env file already exists"
fi

echo ""
echo "📋 Next steps:"
echo "1. Edit .env file with your Supabase credentials"
echo "2. Run: source .env (or export variables manually)"
echo "3. Run: python test_dbf_local.py"
echo "4. Or start Flask app: python flask_app.py"
echo ""
