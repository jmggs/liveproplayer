param(
    [string]$Version = "0.4.2"
)

$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "==> Building Live Pro Player v$Version"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python not found in PATH. Install Python 3 and try again."
}

& python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller not found in current Python environment. Install with: python -m pip install pyinstaller"
}

$innoCompiler = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $innoCompiler) {
    $defaultInno = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (Test-Path $defaultInno) {
        $innoCompiler = $defaultInno
    } else {
        throw "Inno Setup compiler not found. Install Inno Setup 6 or add ISCC to PATH."
    }
} else {
    $innoCompiler = $innoCompiler.Source
}

if (Test-Path ".\\build") { Remove-Item ".\\build" -Recurse -Force }
if (Test-Path ".\\dist") { Remove-Item ".\\dist" -Recurse -Force }

python -m PyInstaller --noconfirm --clean --windowed --name LiveProPlayer --icon "liveproplayer.ico" --add-data "liveproplayer_logo.png;." main.py

& $innoCompiler "/DMyAppVersion=$Version" ".\\installer\\liveproplayer.iss"

Write-Host "==> Done"
Write-Host "Installer generated in .\\dist\\installer"
