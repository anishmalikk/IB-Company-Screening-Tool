# Windows PowerShell Start Script for AI Company Screener
Write-Host "🚀 Starting AI Company Screener..." -ForegroundColor Green

# Function to cleanup on exit
function Cleanup {
    Write-Host "🛑 Stopping servers..." -ForegroundColor Yellow
    Get-Process | Where-Object {$_.ProcessName -eq "python" -and $_.CommandLine -like "*uvicorn*"} | Stop-Process -Force
    Get-Process | Where-Object {$_.ProcessName -eq "python" -and $_.CommandLine -like "*http.server*"} | Stop-Process -Force
    exit 0
}

# Set up signal handlers
trap {
    Cleanup
}

# Kill any existing processes that might be using our ports
Write-Host "🧹 Cleaning up existing processes..." -ForegroundColor Yellow
Get-Process | Where-Object {$_.ProcessName -eq "python" -and $_.CommandLine -like "*uvicorn*"} | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process | Where-Object {$_.ProcessName -eq "python" -and $_.CommandLine -like "*http.server*"} | Stop-Process -Force -ErrorAction SilentlyContinue

# Kill processes using our specific ports
Write-Host "🔌 Freeing up ports..." -ForegroundColor Yellow
$port8000 = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
$port8080 = Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue

if ($port8000) {
    Stop-Process -Id $port8000.OwningProcess -Force -ErrorAction SilentlyContinue
}
if ($port8080) {
    Stop-Process -Id $port8080.OwningProcess -Force -ErrorAction SilentlyContinue
}

# Wait a moment for processes to fully terminate
Start-Sleep -Seconds 2

# Start backend
Write-Host "🚀 Starting backend server..." -ForegroundColor Yellow
Set-Location backend
& ".\venv\Scripts\Activate.ps1"
Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8000" -WindowStyle Hidden
Set-Location ..

# Wait a moment for backend to start
Start-Sleep -Seconds 3

# Start frontend
Write-Host "🌐 Starting frontend server..." -ForegroundColor Yellow
Start-Process -FilePath "python" -ArgumentList "-m", "http.server", "8080" -WindowStyle Hidden

# Wait a moment for frontend to start
Start-Sleep -Seconds 2

Write-Host ""
Write-Host "✅ Servers started!" -ForegroundColor Green
Write-Host ""
Write-Host "📱 Frontend: http://localhost:8080/frontend.html" -ForegroundColor Cyan
Write-Host "🔧 Backend API: http://localhost:8000" -ForegroundColor Cyan
Write-Host "📚 API Docs: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop servers" -ForegroundColor Yellow

# Wait for user to stop
try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
} catch {
    Cleanup
} 