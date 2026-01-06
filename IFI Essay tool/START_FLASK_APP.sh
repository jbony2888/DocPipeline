#!/bin/bash
# Script to start Flask application

cd "$(dirname "$0")"

export SUPABASE_URL="https://escbcdjlafzjxzqiephc.supabase.co"
export SUPABASE_ANON_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVzY2JjZGpsYWZ6anh6cWllcGhjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njc2NzgzNTcsImV4cCI6MjA4MzI1NDM1N30.kxxKhBcp1iZuwSrucZhBx31f59AlW3EO0pu279lIhJI"
export SUPABASE_SERVICE_ROLE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVzY2JjZGpsYWZ6anh6cWllcGhjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NzY3ODM1NywiZXhwIjoyMDgzMjU0MzU3fQ.n5H7DF914ZkvsFcRSQQXpvnMbajATY86TXPpdXJi9xg"
export FLASK_SECRET_KEY="dev-secret-key-12345"
export FLASK_PORT=5000
export WORKER_ID="worker-1"

echo "🚀 Starting Flask application on port ${FLASK_PORT}..."
echo "📧 Update Supabase redirect URL to: http://localhost:${FLASK_PORT}/auth/callback"
echo ""
python flask_app.py

