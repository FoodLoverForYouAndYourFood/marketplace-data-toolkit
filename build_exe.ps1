param(
    [string]$Python = "python",
    [string]$Venv = ".venv",
    [string]$AppName = "ozon_wb_parser"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host ">> Creating venv ($Venv) and installing deps..."
if (-not (Test-Path $Venv)) {
    & $Python -m venv $Venv
}
& "$Venv\\Scripts\\Activate.ps1"
python -m pip install --upgrade pip
if (Test-Path "requirements.txt") {
    pip install -r requirements.txt
} else {
    Write-Warning "requirements.txt not found, installing minimal deps..."
    pip install playwright requests curl_cffi openpyxl
}
pip install pyinstaller

Write-Host ">> Downloading Chromium for Playwright..."
$env:PLAYWRIGHT_BROWSERS_PATH = "0"
python -m playwright install chromium

$browserDir = & $Python -c "from pathlib import Path; import playwright; print(Path(playwright.__file__).parent / '.local-browsers')" 2>$null
$browserArgs = @()
if ($LASTEXITCODE -eq 0 -and $browserDir -and (Test-Path $browserDir)) {
    $browserArgs = @("--add-data", "$browserDir;.local-browsers")
} else {
    Write-Warning "Playwright browsers path not found, skipping embed. Browser will be downloaded on first run."
}

Write-Host ">> Building exe ($AppName.exe)..."
$pyinstallerArgs = @(
  "--noconsole",
  "--onefile",
  "--name", $AppName,
  "--clean",
  "--add-data", "data;data",
  "--collect-all", "playwright"
) + $browserArgs + @("src/app_gui.py")

pyinstaller @pyinstallerArgs

Write-Host "Done. File: dist\\$AppName.exe"
