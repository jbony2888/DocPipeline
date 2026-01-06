#!/bin/bash
# Script to start Flask auth callback service

cd "$(dirname "$0")"

export SUPABASE_URL="https://escbcdjlafzjxzqiephc.supabase.co"
export SUPABASE_ANON_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVzY2JjZGpsYWZ6anh6cWllcGhjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njc2NzgzNTcsImV4cCI6MjA4MzI1NDM1N30.kxxKhBcp1iZuwSrucZhBx31f59AlW3EO0pu279lIhJI"
export STREAMLIT_URL="http://localhost:8501"
export FLASK_SECRET_KEY="dev-secret-key-12345"
export FLASK_PORT=5001

echo "🚀 Starting Flask auth callback service on port 5001..."
echo "📧 Update Supabase redirect URL to: http://localhost:5001/auth/callback"
echo ""
python auth_callback.py

