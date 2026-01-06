#!/bin/bash
# Script to start Flask auth callback service
# IMPORTANT: Set environment variables in .env file or export them before running

cd "$(dirname "$0")"

# Load environment variables from .env if it exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check for required environment variables
if [ -z "$SUPABASE_URL" ]; then
    echo "❌ Error: SUPABASE_URL is not set"
    echo "   Create a .env file or export SUPABASE_URL"
    exit 1
fi

if [ -z "$SUPABASE_ANON_KEY" ]; then
    echo "❌ Error: SUPABASE_ANON_KEY is not set"
    echo "   Create a .env file or export SUPABASE_ANON_KEY"
    exit 1
fi

# Optional variables with defaults
export STREAMLIT_URL=${STREAMLIT_URL:-http://localhost:8501}
export FLASK_SECRET_KEY=${FLASK_SECRET_KEY:-$(python -c "import secrets; print(secrets.token_hex(32))")}
export FLASK_PORT=${FLASK_PORT:-5001}

echo "🚀 Starting Flask auth callback service on port 5001..."
echo "📧 Update Supabase redirect URL to: http://localhost:5001/auth/callback"
echo ""
python auth_callback.py

