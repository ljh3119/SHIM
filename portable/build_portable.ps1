$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "[1/4] Install portable build dependencies"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

Write-Host "[2/4] Build Tailwind CSS output"
npm run build:css

# package.json 버전과 main.py·base.html·compose 태그 불일치 방지(빌드 직전 동기화)
$pkg = Get-Content .\package.json -Raw -Encoding UTF8 | ConvertFrom-Json
& .\tools\scripts\release.ps1 -Version ([string]$pkg.version)

Write-Host "[3/4] Run PyInstaller build"
pyinstaller `
  --noconfirm `
  --clean `
  --name SHIM_Portable `
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
  --add-data "var/data;data" `
  portable/shim_portable.py

Write-Host "[4/4] Copy runtime scripts and initial data to dist folder"
Copy-Item portable\run_portable.bat dist\SHIM_Portable\run_portable.bat -Force
Copy-Item portable\stop_portable.bat dist\SHIM_Portable\stop_portable.bat -Force
Copy-Item portable\README_PORTABLE.md dist\SHIM_Portable\README_PORTABLE.md -Force
if (Test-Path var\data) {
    Copy-Item var\data dist\SHIM_Portable\data -Recurse -Force
}

Write-Host "Done: The final package is ready in 'dist\SHIM_Portable'."
Write-Host "Copy 'dist\SHIM_Portable' to the target offline PC."
