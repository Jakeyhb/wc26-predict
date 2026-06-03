# WC26 Predict — Windows Task Scheduler Registration
# Run once as Administrator to register all daily tasks.
#
# Usage (Administrator PowerShell):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\scripts\register_windows_tasks.ps1
#
# After running, verify with:
#   Get-ScheduledTask -TaskPath "\WC26\" | Format-Table TaskName, State

$ErrorActionPreference = "Stop"

$ProjectRoot = "D:\hermes agent\2026世界杯分析"
$PythonExe = "$ProjectRoot\backend\.venv\Scripts\python.exe"
$DailyOps = "$ProjectRoot\backend\scripts\daily_ops.py"
$TaskPath = "\WC26\"

Write-Host "WC26 Predict — Task Scheduler Registration" -ForegroundColor Cyan
Write-Host "─────────────────────────────────────────────" -ForegroundColor Cyan

# Verify paths
if (-not (Test-Path $PythonExe)) {
    Write-Error "Python not found: $PythonExe"
    exit 1
}
if (-not (Test-Path $DailyOps)) {
    Write-Error "daily_ops.py not found: $DailyOps"
    exit 1
}

Write-Host "Python: $PythonExe"
Write-Host "DailyOps: $DailyOps"
Write-Host ""

# Define tasks
$Tasks = @(
    @{
        Name = "WC26_HealthCheck"
        Time = "06:00"
        Args = "--task health"
        Description = "Daily health check — DB, predictions, data freshness"
    },
    @{
        Name = "WC26_FetchMarket"
        Time = "08:00"
        Args = "--task fetch-market"
        Description = "Fetch T-24h market odds snapshot"
    },
    @{
        Name = "WC26_Pregenerate"
        Time = "09:00"
        Args = "--task pregenerate"
        Description = "Regenerate WC26 group predictions"
    },
    @{
        Name = "WC26_Postmatch"
        Time = "23:00"
        Args = "--task postmatch"
        Description = "Post-match evaluation for today's matches"
    },
    @{
        Name = "WC26_Backup"
        Time = "23:30"
        Args = "--task backup"
        Description = "Backup database + health report"
    }
)

foreach ($Task in $Tasks) {
    $TaskName = $Task.Name
    $Action = New-ScheduledTaskAction -Execute $PythonExe `
        -Argument "$DailyOps $($Task.Args)" `
        -WorkingDirectory "$ProjectRoot\backend"

    $Trigger = New-ScheduledTaskTrigger -Daily -At $Task.Time

    $Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" `
        -LogonType ServiceAccount -RunLevel Highest

    $Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew

    try {
        Register-ScheduledTask -TaskName $TaskName `
            -TaskPath $TaskPath `
            -Action $Action `
            -Trigger $Trigger `
            -Principal $Principal `
            -Settings $Settings `
            -Description $Task.Description `
            -Force | Out-Null

        Write-Host "  [OK] $TaskName @ $($Task.Time)" -ForegroundColor Green
    }
    catch {
        Write-Host "  [FAIL] $TaskName — $_" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Registered tasks under $TaskPath" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Verify: Get-ScheduledTask -TaskPath '\WC26\'"
Write-Host "  2. Test run: Start-ScheduledTask -TaskName 'WC26_HealthCheck'"
Write-Host "  3. Manual checklist reminder before each WC26 match"
Write-Host "     → python $DailyOps --task health"
