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

.PARAMETER Installer
    Also build an Inno Setup installer: dist\AVEN-AI-Setup-<version>.exe (recommended for download).

.PARAMETER BuildBootloader
    Compile PyInstaller's bootloader from source. Antivirus products often flag the stock,
    pre-built bootloader (it is shared with malware); a freshly compiled one avoids most of
    these false positives. Needs the Visual Studio C++ build tools.

.PARAMETER SkipTests
    Skip the pytest run (not recommended for release builds).

.PARAMETER Python
    Python launcher/command to use (default: "py -3.12" if available, else "python").

.NOTES
    Code signing: when AVEN_SIGN_PFX_BASE64 (a base64-encoded .pfx certificate) and
    AVEN_SIGN_PFX_PASSWORD are set, the executable and installer are signed with signtool.

    Set the AVEN_CLOUD_URL environment variable (e.g. https://aven-cloud.onrender.com) to build an
    app that works without an API key through your AVEN Cloud server.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
    powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -OneFile
#>
param(
    [switch]$OneFile,
    [switch]$Installer,
    [switch]$BuildBootloader,
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
if ($BuildBootloader) {
    $pyiVersion = & $VenvPython -c "import PyInstaller; print(PyInstaller.__version__)"
    Write-Host "==> Compiling the PyInstaller $pyiVersion bootloader from source" -ForegroundColor Cyan
    $env:PYINSTALLER_COMPILE_BOOTLOADER = "1"
    Invoke-Checked $VenvPython @("-m", "pip", "install", "--force-reinstall", "--no-deps", "--no-binary", "pyinstaller", "pyinstaller==$pyiVersion")
    Remove-Item Env:PYINSTALLER_COMPILE_BOOTLOADER
}

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

# --- AVEN Local engine ----------------------------------------------------------------
# llama.cpp's llama-server (pinned release, checksum-verified) runs open-source models on the PC.
Write-Host "==> Fetching the AVEN Local engine (llama.cpp)" -ForegroundColor Cyan
Invoke-Checked $VenvPython @("scripts\fetch_engine.py", "--platform", "win-x64")
# Ship the Microsoft C++ runtime next to the engine for PCs that don't have it installed.
$RuntimeSources = @(
    (Join-Path $Venv "Lib\site-packages\PySide6"),
    (Split-Path (& $VenvPython -c "import sys; print(sys.base_prefix + '\\python.exe')"))
)
foreach ($dll in @("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_1.dll")) {
    $target = Join-Path $ProjectRoot "engine\$dll"
    if (-not (Test-Path $target)) {
        foreach ($dir in $RuntimeSources) {
            $candidate = Join-Path $dir $dll
            if (Test-Path $candidate) { Copy-Item $candidate $target; break }
        }
    }
}
Invoke-Checked (Join-Path $ProjectRoot "engine\llama-server.exe") @("--version")

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

# --- code signing (optional) ---------------------------------------------------------------
function Get-SignTool {
    $found = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if ($found) { return $found.FullName }
    return $null
}
$Signing = [bool]($env:AVEN_SIGN_PFX_BASE64 -and $env:AVEN_SIGN_PFX_PASSWORD)
$PfxPath = Join-Path ([System.IO.Path]::GetTempPath()) "aven-signing.pfx"
function Sign-File([string]$Path) {
    if (-not $Signing) { return }
    $signtool = Get-SignTool
    if (-not $signtool) { throw "signtool.exe not found (install the Windows SDK)." }
    Write-Host "==> Signing $Path" -ForegroundColor Cyan
    # Called directly (not via Invoke-Checked) so a failure never prints the certificate password.
    & $signtool sign /f $PfxPath /p $env:AVEN_SIGN_PFX_PASSWORD /fd SHA256 /tr http://timestamp.digicert.com `
        /td SHA256 /d "AVEN AI" $Path
    if ($LASTEXITCODE -ne 0) { throw "Code signing failed for $Path (exit code $LASTEXITCODE)." }
    Invoke-Checked $signtool @("verify", "/pa", $Path)
}
if ($Signing) {
    [System.IO.File]::WriteAllBytes($PfxPath, [Convert]::FromBase64String($env:AVEN_SIGN_PFX_BASE64))
}
try {
    Sign-File $Exe

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

    # --- installer (optional) ---------------------------------------------------------------
    if ($Installer -and -not $OneFile) {
        $iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
        if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
        if (-not (Test-Path $iscc)) {
            Write-Host "==> Installing Inno Setup" -ForegroundColor Cyan
            Invoke-Checked "choco" @("install", "innosetup", "-y", "--no-progress")
            $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
        }
        Write-Host "==> Building the installer" -ForegroundColor Cyan
        Invoke-Checked $iscc @("/Qp", "/DAppVersion=$version", (Join-Path $ProjectRoot "installer\aven_ai.iss"))
        $setup = Join-Path $ProjectRoot "dist\AVEN-AI-Setup-$version.exe"
        if (-not (Test-Path $setup)) { throw "Installer was not created." }
        Sign-File $setup
        Write-Host "Installer: $setup" -ForegroundColor Green
    }
} finally {
    if (Test-Path $PfxPath) { Remove-Item $PfxPath -Force }
}

if ($Signing) {
    Write-Host "The executable and installer are code-signed." -ForegroundColor Green
} else {
    Write-Host "Note: not code-signed (no certificate configured). See RELEASE_CHECKLIST.md." -ForegroundColor Yellow
}
