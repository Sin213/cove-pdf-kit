<#
.SYNOPSIS
    Build Cove PDF Kit into a Windows Setup installer and a single-file
    portable executable.

.DESCRIPTION
    Runs locally on Windows (PowerShell 5.1+ or PowerShell 7) and inside the
    GitHub Actions windows-latest runner. Creates a private venv, installs
    build deps, generates the .ico from the PNG, then runs PyInstaller twice:
      * --onedir  for the Inno Setup installer (Setup.exe)
      * --onefile for the standalone Portable.exe

.EXAMPLE
    .\build.ps1
    .\build.ps1 -Version 1.2.0
#>

[CmdletBinding()]
param(
    # Default of "" means "read it from pyproject.toml" — see below. We
    # can't put the read in the default expression because PowerShell
    # parameter defaults must be constant.
    [string]$Version = ""
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not $Version) {
    # Single source of truth: pyproject.toml. If neither -Version nor a
    # readable pyproject is available, refuse to build instead of shipping
    # a misleading 0.0.0 artifact.
    $pyproject = Join-Path $PSScriptRoot "pyproject.toml"
    if (-not (Test-Path $pyproject)) {
        throw "build.ps1: pyproject.toml not found at $pyproject. Pass -Version <x.y.z> to override."
    }
    $match = Select-String -Path $pyproject -Pattern '^version\s*=\s*"([^"]+)"' |
             Select-Object -First 1
    if (-not $match) {
        throw "build.ps1: could not parse 'version = `"...`"' from pyproject.toml. Pass -Version <x.y.z> to override."
    }
    $Version = $match.Matches[0].Groups[1].Value
}

$App        = "cove-pdf-kit"
$ReleaseDir = "release"

function Step([string]$msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

Step "Building $App v$Version"

# --- 1. Build environment ---------------------------------------------------
Step "[1/5] Creating build venv"
if (Test-Path .buildenv) { Remove-Item -Recurse -Force .buildenv }
python -m venv .buildenv
& .\.buildenv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.buildenv\Scripts\python.exe -m pip install --quiet `
    PySide6 Pillow pypdf pikepdf pypdfium2 pyinstaller

# --- 2. Generate .ico from the PNG ------------------------------------------
Step "[2/5] Generating cove_icon.ico"
& .\.buildenv\Scripts\python.exe -c @"
from PIL import Image
Image.open('cove_icon.png').save(
    'cove_icon.ico',
    sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)],
)
"@

# --- 3. PyInstaller: one-dir (installer input) ------------------------------
Step "[3/5] PyInstaller (one-dir for installer)"
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist)  { Remove-Item -Recurse -Force dist  }

$commonArgs = @(
    '--noconfirm', '--clean', '--log-level', 'WARN',
    '--windowed',
    '--name', $App,
    '--icon', 'cove_icon.ico',
    '--paths', 'src',
    '--add-data', ("src\cove_pdf_kit\assets\cove_icon.png" + [IO.Path]::PathSeparator + "cove_pdf_kit\assets"),
    '--collect-binaries', 'pypdfium2_raw',
    '--collect-binaries', 'pikepdf',
    '--exclude-module', 'PySide6.QtWebEngineCore',
    '--exclude-module', 'PySide6.QtWebEngineWidgets',
    '--exclude-module', 'PySide6.QtQml',
    '--exclude-module', 'PySide6.QtQuick',
    '--exclude-module', 'PySide6.QtPdf',
    '--exclude-module', 'PySide6.Qt3DCore',
    '--exclude-module', 'PySide6.QtCharts',
    '--exclude-module', 'PySide6.QtDataVisualization',
    '--exclude-module', 'PySide6.QtMultimedia',
    '--exclude-module', 'PySide6.QtMultimediaWidgets',
    '--exclude-module', 'tkinter',
    'packaging\launcher.py'
)

& .\.buildenv\Scripts\pyinstaller.exe @commonArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller (onedir) failed" }

$dirAppDir = Join-Path 'dist' $App
Copy-Item cove_icon.png $dirAppDir -Force
if (Test-Path README.md) { Copy-Item README.md $dirAppDir -Force }
if (Test-Path LICENSE)   { Copy-Item LICENSE   $dirAppDir -Force }

# --- 4. PyInstaller: one-file (portable) ------------------------------------
Step "[4/5] PyInstaller (one-file portable)"
$portableName = "$App-portable"
& .\.buildenv\Scripts\pyinstaller.exe `
    --noconfirm --clean --log-level WARN `
    --onefile --windowed `
    --name $portableName `
    --icon cove_icon.ico `
    --paths src `
    --add-data ("src\cove_pdf_kit\assets\cove_icon.png" + [IO.Path]::PathSeparator + "cove_pdf_kit\assets") `
    --collect-binaries pypdfium2_raw `
    --collect-binaries pikepdf `
    --exclude-module PySide6.QtWebEngineCore `
    --exclude-module PySide6.QtWebEngineWidgets `
    --exclude-module PySide6.QtQml `
    --exclude-module PySide6.QtQuick `
    --exclude-module PySide6.QtPdf `
    --exclude-module PySide6.Qt3DCore `
    --exclude-module PySide6.QtCharts `
    --exclude-module PySide6.QtDataVisualization `
    --exclude-module PySide6.QtMultimedia `
    --exclude-module PySide6.QtMultimediaWidgets `
    --exclude-module tkinter `
    packaging\launcher.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller (onefile) failed" }

# --- 5. Build installer + stage portable ------------------------------------
Step "[5/5] Building Setup installer with Inno Setup"
New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null

$iscc = $null
foreach ($candidate in @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)) {
    if ($candidate -and (Test-Path $candidate)) { $iscc = $candidate; break }
}
if (-not $iscc) {
    $inPath = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($inPath) { $iscc = $inPath.Source }
}
if (-not $iscc) { throw "Inno Setup (iscc.exe) not found. Install Inno Setup 6." }

$absSource  = (Resolve-Path $dirAppDir).Path
$absRelease = (Resolve-Path $ReleaseDir).Path
$absIcon    = (Resolve-Path cove_icon.ico).Path

& $iscc `
    "/DAppVersion=$Version" `
    "/DSourceDir=$absSource" `
    "/DOutputDir=$absRelease" `
    "/DIconFile=$absIcon" `
    packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed" }

Step "Staging portable exe"
$portableSrc  = Join-Path 'dist' "$portableName.exe"
$portableDest = Join-Path $ReleaseDir ("{0}-{1}-Portable.exe" -f $App, $Version)
if (Test-Path $portableDest) { Remove-Item -Force $portableDest }
Copy-Item $portableSrc $portableDest -Force

Remove-Item -Recurse -Force .buildenv, build, dist, cove_icon.ico -ErrorAction SilentlyContinue
Get-ChildItem -Filter *.spec | Remove-Item -Force -ErrorAction SilentlyContinue

Step "Done. Artifacts:"
Get-ChildItem $ReleaseDir | Format-Table Name, Length -AutoSize
