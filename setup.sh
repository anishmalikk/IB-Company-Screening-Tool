#!/bin/bash

echo "🚀 Setting up AI Company Screener for Demo"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "backend/venv" ]; then
    echo "📦 Creating virtual environment..."
    cd backend
    python3 -m venv venv
    cd ..
fi

# Activate virtual environment and install dependencies
echo "📦 Installing dependencies..."
cd backend
source venv/bin/activate

# Install required packages
pip install fastapi uvicorn requests beautifulsoup4 playwright openai serpapi python-dotenv

# Install Playwright browsers
playwright install

cd ..

echo "✅ Setup complete!"
echo ""
echo "🎯 To start the demo:"
echo "1. Backend: cd backend && source venv/bin/activate && uvicorn main:app --reload --host 0.0.0.0 --port 8000"
echo "2. Frontend: python -m http.server 8080"
echo "3. Open: http://localhost:8080/frontend.html"
echo ""
echo "📋 Demo Checklist:"
echo "□ Test with 'Apple Inc.' / 'AAPL'"
echo "□ Test with 'Microsoft Corporation' / 'MSFT'"
echo "□ Show executive extraction"
echo "□ Show industry analysis"
echo "□ Show 10-Q processing" 