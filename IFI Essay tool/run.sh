#!/bin/bash
# Quick start script for EssayFlow

echo "🚀 Starting EssayFlow..."
echo ""

# Navigate to script directory
cd "$(dirname "$0")"

# Activate virtual environment
if [ -d ".venv" ]; then
    echo "✅ Activating virtual environment..."
    source .venv/bin/activate
else
    echo "❌ Virtual environment not found!"
    echo "Please run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Ensure directories exist
mkdir -p artifacts outputs

# Run Streamlit
echo "✅ Starting Streamlit app..."
echo ""
echo "📝 EssayFlow will open in your browser at http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

streamlit run app.py


