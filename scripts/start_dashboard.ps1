# start_dashboard.ps1 — Launch WC26 Predict Streamlit Dashboard
# Usage: powershell -File scripts/start_dashboard.ps1
#        powershell -File scripts/start_dashboard.ps1 -Port 8502

param(
    [int]$Port = 8501,
    [string]$Address = "localhost"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..\backend")).Path

# Check project root exists
if (-not (Test-Path $ProjectRoot)) {
    Write-Error "Backend path not found: $ProjectRoot"
    Write-Error "Please update `$ProjectRoot` in this script to match your local path."
    exit 1
}

Set-Location $ProjectRoot

# Activate venv if present
$VenvActivate = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $VenvActivate) {
    & $VenvActivate
} else {
    Write-Error "Virtual environment not found at $VenvActivate."
    Write-Error "Run: python -m venv .venv && .\.venv\Scripts\Activate.ps1 && pip install -r requirements.txt"
    exit 1
}

# Set encoding (critical for Chinese Windows / GBK)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# Change to backend directory
Set-Location $ProjectRoot

Write-Host "============================================="
Write-Host "  WC26 Predict Local Studio V3.5 test"
Write-Host "============================================="
Write-Host "  Port:     $Port"
Write-Host "  URL:      http://${Address}:${Port}"
Write-Host "  Python:   $(python --version)"
Write-Host "  Encoding: UTF-8"
Write-Host "============================================="
Write-Host ""

# Launch Streamlit
streamlit run dashboard/app.py `
    --server.port $Port `
    --server.address $Address `
    --server.headless true `
    --theme.base "dark" `
    --theme.primaryColor "#00BFFF"

# Deactivate on exit
deactivate
