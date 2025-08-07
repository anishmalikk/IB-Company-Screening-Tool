Write-Host "Starting AI Company Screener..." -ForegroundColor Green

function Cleanup {
    Write-Host "Stopping servers..." -ForegroundColor Red
    Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*uvicorn*" } | Stop-Process -Force -ErrorAction SilentlyContinue
    Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*http.server*" } | Stop-Process -Force -ErrorAction SilentlyContinue
    exit
}

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

Write-Host "Starting backend server..." -ForegroundColor Yellow
Set-Location backend
& .\venv\Scripts\Activate.ps1
Start-Process -FilePath python -ArgumentList "-m", "uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8000" -WindowStyle Hidden
Set-Location ..

Start-Sleep -Seconds 3

Write-Host "Starting frontend server..." -ForegroundColor Yellow
Start-Process -FilePath python -ArgumentList "-m", "http.server", "8080" -WindowStyle Hidden

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "Servers started successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Frontend: http://localhost:8080/frontend.html" -ForegroundColor Cyan
Write-Host "Backend API: http://localhost:8000" -ForegroundColor Cyan
Write-Host "API Docs: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop servers" -ForegroundColor Magenta

while ($true) {
    Start-Sleep -Seconds 1
}