<#
.SYNOPSIS
    Builds the AVEN AI Desktop Windows executable with PyInstaller.

.DESCRIPTION
    Creates an isolated build virtual environment, installs pinned dependencies,
    runs the test suite, regenerates the icon and runs PyInstaller.

    Output (folder build, recommended):  dist\AVEN AI\AVEN AI.exe
    Output (-OneFile):                    dist\AVEN AI.exe

.PARAMETER OneFile
    Also produce a single-file executable instead of the folder build.

.PARAMETER SkipTests
    Skip the pytest run (not recommended for release builds).

.PARAMETER Python
    Python launcher/command to use (default: "py -3.12" if available, else "python").

.NOTES
    Set the AVEN_CLOUD_URL environment variable (e.g. https://aven-cloud.onrender.com) to build an
    app that works without an API key through your AVEN Cloud server.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
    powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -OneFile
#>
param(
    [switch]$OneFile,
    [switch]$SkipTests,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Exe $($Arguments -join ' ')" }
}

# --- choose Python -----------------------------------------------------------------
if (-not $Python) {
    $hasPy = Get-Command py -ErrorAction SilentlyContinue
    if ($hasPy) {
        # Probe for 3.12 without letting the launcher's stderr abort the script.
        $previous = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & py -3.12 -c "import sys" 2>$null | Out-Null
        $probe = $LASTEXITCODE
        $ErrorActionPreference = $previous
        if ($probe -eq 0) { $Python = "py -3.12" } else { $Python = "py -3" }
    } else {
        $Python = "python"
    }
}
$pyParts = $Python.Split(" ")
$pyExe = $pyParts[0]
$pyArgs = @()
if ($pyParts.Length -gt 1) { $pyArgs = $pyParts[1..($pyParts.Length - 1)] }

Write-Host "==> Using Python: $Python" -ForegroundColor Cyan
Invoke-Checked $pyExe ($pyArgs + @("-c", "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ required'; print(sys.version)"))

# --- build environment -------------------------------------------------------------
$Venv = Join-Path $ProjectRoot ".venv-build"
if (-not (Test-Path $Venv)) {
    Write-Host "==> Creating build virtual environment" -ForegroundColor Cyan
    Invoke-Checked $pyExe ($pyArgs + @("-m", "venv", $Venv))
}
$VenvPython = Join-Path $Venv "Scripts\python.exe"

Write-Host "==> Installing dependencies" -ForegroundColor Cyan
Invoke-Checked $VenvPython @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked $VenvPython @("-m", "pip", "install", "-r", "requirements-dev.txt")

# --- tests -------------------------------------------------------------------------
if (-not $SkipTests) {
    Write-Host "==> Running tests" -ForegroundColor Cyan
    $env:QT_QPA_PLATFORM = "offscreen"
    Invoke-Checked $VenvPython @("-m", "pytest", "-q")
    Remove-Item Env:QT_QPA_PLATFORM
}

# --- icon --------------------------------------------------------------------------
Write-Host "==> Generating icon" -ForegroundColor Cyan
Invoke-Checked $VenvPython @("scripts\generate_icon.py")

# --- AVEN Cloud address -------------------------------------------------------------
# The server address is public (no secrets). Without it, users must add their own API key.
$CloudFile = Join-Path $ProjectRoot "assets\cloud.json"
if ($env:AVEN_CLOUD_URL) {
    Write-Host "==> Using AVEN Cloud server: $($env:AVEN_CLOUD_URL)" -ForegroundColor Cyan
    @{ url = $env:AVEN_CLOUD_URL } | ConvertTo-Json | Set-Content -Encoding UTF8 $CloudFile
} elseif (Test-Path $CloudFile) {
    Write-Host "==> Using existing assets\cloud.json" -ForegroundColor Cyan
} else {
    Write-Host "==> No AVEN_CLOUD_URL set: this build needs users to add their own API key." -ForegroundColor Yellow
}

# --- PyInstaller -------------------------------------------------------------------
if ($OneFile) { $env:AVEN_ONEFILE = "1" } else { Remove-Item Env:AVEN_ONEFILE -ErrorAction SilentlyContinue }
Write-Host "==> Running PyInstaller" -ForegroundColor Cyan
Invoke-Checked $VenvPython @("-m", "PyInstaller", "--noconfirm", "--clean", "aven_ai.spec")
Remove-Item Env:AVEN_ONEFILE -ErrorAction SilentlyContinue

if ($OneFile) {
    $Exe = Join-Path $ProjectRoot "dist\AVEN AI.exe"
} else {
    $Exe = Join-Path $ProjectRoot "dist\AVEN AI\AVEN AI.exe"
}
if (-not (Test-Path $Exe)) { throw "Build finished but $Exe was not found." }

$version = & $VenvPython -c "from app.version import __version__; print(__version__)"
Write-Host ""
Write-Host "Build complete: AVEN AI Desktop $version" -ForegroundColor Green
Write-Host "Executable: $Exe" -ForegroundColor Green
if (-not $OneFile) {
    $zip = Join-Path $ProjectRoot "dist\AVEN-AI-Desktop-$version-win64.zip"
    if (Test-Path $zip) { Remove-Item $zip }
    Compress-Archive -Path (Join-Path $ProjectRoot "dist\AVEN AI") -DestinationPath $zip
    Write-Host "Zip archive: $zip" -ForegroundColor Green
}
Write-Host "Note: the executable is NOT code-signed. See RELEASE_CHECKLIST.md." -ForegroundColor Yellow
