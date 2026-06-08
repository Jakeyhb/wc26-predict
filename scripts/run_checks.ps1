<#
.SYNOPSIS
    WC26 Predict — 统一项目健康检查脚本
.DESCRIPTION
    从 repository root 执行：.\scripts\run_checks.ps1
    默认 fail-fast：关键检查失败退出非零。
    报告模式：.\scripts\run_checks.ps1 -ReportOnly（运行全部，汇总失败）
.NOTES
    禁止硬编码本机路径。所有路径从脚本自身位置自动推导。
#>

param(
    [switch] $ReportOnly
)

$ErrorActionPreference = "Stop"
$exitCode = 0
$failures = @()
$totalChecks = 0
$passCount = 0
$failCount = 0
$skipCount = 0

# ---- 自动推导路径 ----
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path "$ScriptDir\.."
$BackendDir = Join-Path $RepoRoot "backend"
$TestsDir = Join-Path $BackendDir "tests"
$VenvDir = Join-Path $BackendDir ".venv"
$HealthCheckScript = Join-Path $BackendDir "scripts\health_check.py"

# ---- 辅助函数 ----
function Write-CheckResult {
    param(
        [string] $Status,
        [string] $Name,
        [string] $Detail = ""
    )
    $tag = switch ($Status) {
        "PASS" { "[PASS]" }
        "FAIL" { "[FAIL]" }
        "SKIP" { "[SKIP]" }
        default { "[????]" }
    }
    $line = "$tag $Name"
    if ($Detail) {
        $line += " — $Detail"
    }
    Write-Host $line
}

function Record-Result {
    param(
        [string] $Status,
        [string] $Name,
        [string] $Detail = ""
    )
    $script:totalChecks++
    switch ($Status) {
        "PASS" { $script:passCount++ }
        "FAIL" {
            $script:failCount++
            $script:failures += "$Name : $Detail"
            if (-not $ReportOnly) {
                $script:exitCode = 1
            }
        }
        "SKIP" { $script:skipCount++ }
    }
    Write-CheckResult -Status $Status -Name $Name -Detail $Detail
}

# ---- 查找 Python ----
function Find-Python {
    # 优先使用 .venv
    $venvPython = Join-Path $VenvDir "Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    # Fallback: 系统 python
    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if ($systemPython) {
        return $systemPython.Source
    }
    return $null
}

# ============================================================
# 检查开始
# ============================================================
Write-Host ""
Write-Host "=== WC26 Predict — Health Check ===" -ForegroundColor Cyan
Write-Host "Repo root : $RepoRoot"
Write-Host "Backend   : $BackendDir"
Write-Host "Mode      : $(if ($ReportOnly) { 'ReportOnly' } else { 'FailFast' })"
Write-Host ""

# ---- 0. 目录存在性检查 ----
Write-Host "-- Directory checks --" -ForegroundColor DarkGray

if (Test-Path $BackendDir -PathType Container) {
    Record-Result "PASS" "backend directory exists"
} else {
    Record-Result "FAIL" "backend directory exists" "backend/ not found at $BackendDir"
}

if (Test-Path $TestsDir -PathType Container) {
    Record-Result "PASS" "tests directory exists"
} else {
    Record-Result "SKIP" "tests directory exists" "tests/ not found at $TestsDir"
}

if (Test-Path $VenvDir -PathType Container) {
    Record-Result "PASS" ".venv exists"
} else {
    Record-Result "SKIP" ".venv exists" ".venv/ not found at $VenvDir"
}

# ---- 1. Python version ----
Write-Host ""
Write-Host "-- Python --" -ForegroundColor DarkGray

$pythonPath = Find-Python
if (-not $pythonPath) {
    Record-Result "FAIL" "Python executable" "No Python found in .venv or PATH"
    # 没有 Python 没法继续，退出
    Write-Host ""
    Write-Host "=== Summary ===" -ForegroundColor Cyan
    Write-Host "Total : $totalChecks | PASS: $passCount | FAIL: $failCount | SKIP: $skipCount"
    if ($failCount -gt 0) {
        Write-Host "Failures:" -ForegroundColor Red
        $failures | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    }
    exit 1
}

$pythonVersion = & $pythonPath --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Record-Result "PASS" "Python version" "$pythonVersion"
} else {
    Record-Result "FAIL" "Python version" "python --version returned non-zero"
}

# ---- 2. Import smoke ----
Write-Host ""
Write-Host "-- Import smoke --" -ForegroundColor DarkGray

$coreModules = @(
    "app.main",
    "app.services.prediction_core",
    "app.services.prediction_pipeline",
    "app.services.prediction_enhanced",
    "app.services.postmatch",
    "app.services.learning_engine",
    "app.services.weights",
    "app.services.market.probability"
)

# Write a temp Python script to avoid PowerShell string-escaping issues
$importScriptPath = Join-Path $RepoRoot "scripts\.run_checks_import_smoke.py"
$moduleLines = ($coreModules | ForEach-Object { "    '$_'," }) -join "`n"
@"
import sys, importlib
sys.path.insert(0, r'$BackendDir')
modules = [
$moduleLines
]
failed = []
for m in modules:
    try:
        importlib.import_module(m)
        print(f'OK {m}')
    except Exception as e:
        failed.append(f'{m}: {e}')
        print(f'FAIL {m}: {e}')
if failed:
    print(f'\n{len(failed)} import(s) failed')
    raise SystemExit(1)
else:
    print(f'\nAll {len(modules)} core modules imported successfully')
"@ | Set-Content -Path $importScriptPath -Encoding UTF8

try {
    $importOutput = & $pythonPath $importScriptPath 2>&1
    if ($LASTEXITCODE -eq 0) {
        Record-Result "PASS" "Import core modules" "All $($coreModules.Count) modules imported"
    } else {
        Record-Result "FAIL" "Import core modules" "Some imports failed — see detail below"
        Write-Host $importOutput
    }
} finally {
    Remove-Item $importScriptPath -ErrorAction SilentlyContinue
}

# ---- 3. Compile check (syntax only) ----
Write-Host ""
Write-Host "-- Compile check --" -ForegroundColor DarkGray

$appDir = Join-Path $BackendDir "app"
if (Test-Path $appDir -PathType Container) {
    $compileOutput = & $pythonPath -m compileall -q "$appDir" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Record-Result "PASS" "compileall backend/app" "No syntax errors"
    } else {
        Record-Result "FAIL" "compileall backend/app" "Syntax errors detected"
        Write-Host "  $compileOutput" -ForegroundColor Red
    }
} else {
    Record-Result "SKIP" "compileall backend/app" "backend/app/ not found"
}

# ---- 4. pytest ----
Write-Host ""
Write-Host "-- Pytest --" -ForegroundColor DarkGray

if (Test-Path $TestsDir -PathType Container) {
    $pytestOutput = & $pythonPath -m pytest "$TestsDir" -q --tb=short 2>&1
    $pytestExit = $LASTEXITCODE
    if ($pytestExit -eq 0) {
        Record-Result "PASS" "pytest" "All tests passed"
    } elseif ($pytestExit -eq 5) {
        # pytest exit code 5 = no tests collected
        Record-Result "SKIP" "pytest" "No tests collected"
    } else {
        Record-Result "FAIL" "pytest" "Tests failed (exit code $pytestExit)"
        Write-Host ""
        Write-Host $pytestOutput
    }
} else {
    Record-Result "SKIP" "pytest" "tests/ directory not found"
}

# ---- 5. health_check.py ----
Write-Host ""
Write-Host "-- Health check --" -ForegroundColor DarkGray

if (Test-Path $HealthCheckScript) {
    $origEncoding = $env:PYTHONIOENCODING
    try {
        $env:PYTHONIOENCODING = "utf-8"
        $healthOutput = & $pythonPath $HealthCheckScript 2>&1
    } finally {
        if ($origEncoding) { $env:PYTHONIOENCODING = $origEncoding } else { Remove-Item Env:\PYTHONIOENCODING -ErrorAction SilentlyContinue }
    }
    if ($LASTEXITCODE -eq 0) {
        Record-Result "PASS" "health_check.py" "Health check passed"
    } else {
        Record-Result "FAIL" "health_check.py" "Health check failed (exit code $LASTEXITCODE)"
        Write-Host $healthOutput
    }
} else {
    Record-Result "SKIP" "health_check.py" "Script not found at backend\scripts\health_check.py"
}

# ============================================================
# Summary
# ============================================================
Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Total : $totalChecks | PASS: $passCount | FAIL: $failCount | SKIP: $skipCount"

if ($failCount -gt 0) {
    Write-Host ""
    Write-Host "Failures:" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }

    if ($ReportOnly) {
        Write-Host ""
        Write-Host "[ReportOnly mode — all checks completed, failures listed above]" -ForegroundColor Yellow
    }
}

Write-Host ""

if ($ReportOnly) {
    exit 0
} else {
    exit $exitCode
}
