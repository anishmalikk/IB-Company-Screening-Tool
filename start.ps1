Write-Host "Starting AI Company Screener..." -ForegroundColor Green

function Cleanup {
    Write-Host "Stopping servers..." -ForegroundColor Red
    Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*uvicorn*" } | Stop-Process -Force -ErrorAction SilentlyContinue
    Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*http.server*" } | Stop-Process -Force -ErrorAction SilentlyContinue
    exit
}

# Register cleanup on script exit
Register-EngineEvent PowerShell.Exiting -Action { Cleanup }

Write-Host "Cleaning up existing processes..." -ForegroundColor Yellow
Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*uvicorn*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*http.server*" } | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host "Freeing up ports..." -ForegroundColor Yellow
$ports = @(8000, 8080)
foreach ($port in $ports) {
    $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    foreach ($conn in $conns) {
        if ($conn.OwningProcess) {
            Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}

Start-Sleep -Seconds 2

# Check if virtual environment exists
if (-not (Test-Path "backend\venv")) {
    Write-Host "Virtual environment not found. Please run setup.ps1 first!" -ForegroundColor Red
    exit 1
}

Write-Host "Starting backend server..." -ForegroundColor Yellow
Set-Location backend
& .\venv\Scripts\Activate.ps1

# Start backend server
$backendProcess = Start-Process -FilePath python -ArgumentList "-m", "uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8000" -WindowStyle Hidden -PassThru
Set-Location ..

Start-Sleep -Seconds 3

Write-Host "Starting frontend server..." -ForegroundColor Yellow
# Start frontend server
$frontendProcess = Start-Process -FilePath python -ArgumentList "-m", "http.server", "8080" -WindowStyle Hidden -PassThru

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "Servers started successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Frontend: http://localhost:8080/frontend.html" -ForegroundColor Cyan
Write-Host "Backend API: http://localhost:8000" -ForegroundColor Cyan
Write-Host "API Docs: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop servers" -ForegroundColor Magenta

try {
    while ($true) {
        Start-Sleep -Seconds 1
        
        # Check if processes are still running
        if ($backendProcess.HasExited -or $frontendProcess.HasExited) {
            Write-Host "One or more servers have stopped unexpectedly" -ForegroundColor Red
            break
        }
    }
} catch {
    Write-Host "Stopping servers..." -ForegroundColor Yellow
    if ($backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($frontendProcess -and -not $frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
    }
}