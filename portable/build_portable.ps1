$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "[1/4] Install portable build dependencies"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

Write-Host "[2/4] Build Tailwind CSS output"
npm run build:css
$cssPath = "src\static\css\tailwind.css"
if (-not (Test-Path $cssPath)) {
    throw "Tailwind CSS output file does not exist: $cssPath"
}
$cssFile = Get-Item $cssPath
if ($cssFile.Length -eq 0) {
    throw "Tailwind CSS output file is 0 bytes: $cssPath"
}
Write-Host "Tailwind CSS output verified: $cssPath ($($cssFile.Length) bytes)"

# package.json 버전과 main.py·base.html·compose 태그 불일치 방지(빌드 직전 동기화)
$pkg = Get-Content .\package.json -Raw -Encoding UTF8 | ConvertFrom-Json
& .\tools\scripts\release.ps1 -Version ([string]$pkg.version)

Write-Host "[3/4] Run PyInstaller build"
pyinstaller `
  --noconfirm `
  --clean `
  --name SHIM_Portable `
  --icon "src/static/favicon.ico" `
  --paths "." `
  --collect-submodules src.app `
  --collect-submodules holidays `
  --collect-data holidays `
  --hidden-import src.app.main `
  --exclude-module PIL `
  --exclude-module watchfiles `
  --exclude-module setuptools `
  --exclude-module numpy `
  --exclude-module matplotlib `
  --exclude-module tkinter `
  --exclude-module _tkinter `
  --exclude-module pytest `
  --exclude-module unittest `
  --exclude-module IPython `
  --add-data "src/templates;templates" `
  --add-data "src/static;static" `
  portable/shim_portable.py

Write-Host "[4/4] Copy runtime scripts and initial data to dist folder"
Copy-Item portable\stop_portable.bat dist\SHIM_Portable\stop_portable.bat -Force
Copy-Item portable\README_PORTABLE.md dist\SHIM_Portable\README_PORTABLE.md -Force
if (Test-Path var\data) {
    Copy-Item var\data dist\SHIM_Portable\data -Recurse -Force
}

# Post-Build Hook: Clean up unnecessary development artifacts in the final package
Write-Host "Running Post-Build Hook: Cleaning up unnecessary development artifacts in 'dist\SHIM_Portable\data'..."
$targetDataDir = "dist\SHIM_Portable\data"
if (Test-Path $targetDataDir) {
    # Remove SQLite temporary WAL/SHM locks and actual development database files
    Get-ChildItem -Path $targetDataDir -Filter "*.db-wal" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force
    Get-ChildItem -Path $targetDataDir -Filter "*.db-shm" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force
    Get-ChildItem -Path $targetDataDir -Filter "*.db" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force
    Get-ChildItem -Path $targetDataDir -Filter "*_corrupted*" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force
    
    # Remove development secret keys to ensure zero-config random key generation on production site
    if (Test-Path "$targetDataDir\secret.key") {
        Remove-Item "$targetDataDir\secret.key" -Force
        Write-Host "Removed development secret.key for security and zero-config dynamic generation."
    }
    
    # Remove backup databases and test databases
    Get-ChildItem -Path $targetDataDir -Filter "*.bak" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force
    Get-ChildItem -Path $targetDataDir -Filter "*_test.db" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force
}

Write-Host "Done: The final package is ready in 'dist\SHIM_Portable'."
Write-Host "Copy 'dist\SHIM_Portable' to the target offline PC."
