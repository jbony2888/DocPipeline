#!/bin/bash
# Script to start Flask application
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
export FLASK_PORT=${FLASK_PORT:-5000}
export WORKER_ID=${WORKER_ID:-worker-1}

echo "🚀 Starting Flask application on port ${FLASK_PORT}..."
echo "📧 Update Supabase redirect URL to: http://localhost:${FLASK_PORT}/auth/callback"
echo ""
python flask_app.py

