$ErrorActionPreference = "Stop"

$rootDir = $PSScriptRoot
$backendDir = Join-Path $rootDir "backend"
$frontendDir = Join-Path $rootDir "frontend"
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Host "[HATA] Backend sanal ortami bulunamadi: $pythonExe" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Host "[HATA] Frontend node_modules bulunamadi. Once frontend klasorunde 'npm install' calistirin." -ForegroundColor Red
    exit 1
}

Write-Host "Backend baslatiliyor (http://localhost:8000)..." -ForegroundColor Cyan
Start-Process powershell -WorkingDirectory $backendDir -ArgumentList @(
    "-NoExit",
    "-Command",
    "`$Host.UI.RawUI.WindowTitle = 'Backend - FastAPI (:8000)'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
)

Start-Sleep -Seconds 2

Write-Host "Frontend baslatiliyor (http://localhost:3000)..." -ForegroundColor Green
Start-Process powershell -WorkingDirectory $frontendDir -ArgumentList @(
    "-NoExit",
    "-Command",
    "`$Host.UI.RawUI.WindowTitle = 'Frontend - Next.js (:3000)'; npm run dev"
)

Write-Host ""
Write-Host "Her iki servis de yeni pencerelerde baslatildi!" -ForegroundColor Yellow
Write-Host "  Studio : http://localhost:3000"
Write-Host "  API Doc: http://localhost:8000/docs"
Write-Host ""
Write-Host "Kapatmak icin acilan pencerelerde Ctrl+C yapabilir veya pencereleri kapatabilirsin."
