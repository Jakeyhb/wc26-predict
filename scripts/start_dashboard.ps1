# start_dashboard.ps1 — Launch WC26 Predict Streamlit Dashboard
# Usage: powershell -File scripts/start_dashboard.ps1
#        powershell -File scripts/start_dashboard.ps1 -Port 8502

param(
    [int]$Port = 8501,
    [string]$Address = "localhost"
)

$ProjectRoot = "D:\hermes agent\2026世界杯分析\backend"
$VenvPath = Join-Path $ProjectRoot ".venv"

# Check venv
if (-not (Test-Path $VenvPath)) {
    Write-Error "Virtual environment not found at $VenvPath."
    Write-Error "Run: python -m venv .venv && .\.venv\Scripts\Activate.ps1 && pip install -r requirements.txt"
    exit 1
}

# Activate venv
& "$VenvPath\Scripts\Activate.ps1"

# Set encoding (critical for Chinese Windows / GBK)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# Change to backend directory
Set-Location $ProjectRoot

Write-Host "============================================="
Write-Host "  WC26 Predict Local Studio v2.4"
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
