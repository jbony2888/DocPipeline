#!/bin/bash
# Start EssayFlow with Google Cloud Vision credentials

cd "$(dirname "$0")"

# Set Google Cloud credentials using JSON content method (bypasses file permission issues)
export GOOGLE_CLOUD_VISION_CREDENTIALS_JSON=$(cat /Users/jerrybony/Downloads/youtube-ai-tool-478918-1941d902d881.json)

# Source virtual environment
source .venv/bin/activate

# Start Streamlit
echo "🚀 Starting EssayFlow with Google Cloud Vision..."
echo "📝 App will open at http://localhost:8501"
echo ""
streamlit run app.py

