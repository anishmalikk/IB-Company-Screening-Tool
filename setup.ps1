# Windows PowerShell Setup Script for AI Company Screener
Write-Host "🚀 Setting up AI Company Screener for Demo" -ForegroundColor Green

# Check if Python is installed
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Python is required but not installed" -ForegroundColor Red
        Write-Host "Please install Python 3.8+ from https://python.org" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python is required but not installed" -ForegroundColor Red
    Write-Host "Please install Python 3.8+ from https://python.org" -ForegroundColor Yellow
    exit 1
}

# Create virtual environment if it doesn't exist
if (-not (Test-Path "backend\venv")) {
    Write-Host "📦 Creating virtual environment..." -ForegroundColor Yellow
    Set-Location backend
    python -m venv venv
    Set-Location ..
}

# Activate virtual environment and install dependencies
Write-Host "📦 Installing dependencies..." -ForegroundColor Yellow
Set-Location backend
& ".\venv\Scripts\Activate.ps1"

# Install required packages
pip install fastapi uvicorn requests beautifulsoup4 playwright openai serpapi python-dotenv aiofiles spacy nltk

# Install Playwright browsers
playwright install

Set-Location ..

Write-Host "✅ Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "🎯 To start the demo:" -ForegroundColor Cyan
Write-Host "1. Backend: cd backend && .\venv\Scripts\Activate.ps1 && uvicorn main:app --reload --host 0.0.0.0 --port 8000" -ForegroundColor White
Write-Host "2. Frontend: python -m http.server 8080" -ForegroundColor White
Write-Host "3. Open: http://localhost:8080/frontend.html" -ForegroundColor White
Write-Host ""
Write-Host "📋 Demo Checklist:" -ForegroundColor Cyan
Write-Host "□ Test with 'Apple Inc.' / 'AAPL'" -ForegroundColor White
Write-Host "□ Test with 'Microsoft Corporation' / 'MSFT'" -ForegroundColor White
Write-Host "□ Show executive extraction" -ForegroundColor White
Write-Host "□ Show industry analysis" -ForegroundColor White
Write-Host "□ Show 10-Q processing" -ForegroundColor White 