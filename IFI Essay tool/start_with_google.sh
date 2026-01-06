#!/bin/bash
# Start EssayFlow with Google Cloud Vision credentials

cd "$(dirname "$0")"

# Set Google Cloud credentials using JSON content method (bypasses file permission issues)
# Update this path to point to your own Google Cloud service account JSON file
GOOGLE_CREDENTIALS_FILE=${GOOGLE_CREDENTIALS_FILE:-./credentials.json}
if [ ! -f "$GOOGLE_CREDENTIALS_FILE" ]; then
    echo "❌ Error: Google Cloud credentials file not found at $GOOGLE_CREDENTIALS_FILE"
    echo "   Set GOOGLE_CREDENTIALS_FILE environment variable or place credentials.json in the project root"
    exit 1
fi
export GOOGLE_CLOUD_VISION_CREDENTIALS_JSON=$(cat "$GOOGLE_CREDENTIALS_FILE")

# Source virtual environment
source .venv/bin/activate

# Start Streamlit
echo "🚀 Starting EssayFlow with Google Cloud Vision..."
echo "📝 App will open at http://localhost:8501"
echo ""
streamlit run app.py

