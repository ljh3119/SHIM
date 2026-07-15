$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

function Assert-LastExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

Write-Host "[1/4] Install portable build dependencies"
python -m pip install -r requirements.txt pyinstaller
Assert-LastExitCode "portable dependency install"

Write-Host "[2/4] Build Tailwind CSS output"
npm run build:css
Assert-LastExitCode "Tailwind CSS build"
$cssPath = "src\static\css\tailwind.css"
if (-not (Test-Path $cssPath)) {
    throw "Tailwind CSS output file does not exist: $cssPath"
}
$cssFile = Get-Item $cssPath
if ($cssFile.Length -eq 0) {
    throw "Tailwind CSS output file is 0 bytes: $cssPath"
}
Write-Host "Tailwind CSS output verified: $cssPath ($($cssFile.Length) bytes)"

# package.json 버전과 런타임 상수·compose 태그·배포 문서 불일치 방지(빌드 직전 동기화)
$pkg = Get-Content .\package.json -Raw -Encoding UTF8 | ConvertFrom-Json
$version = [string]$pkg.version
& .\tools\scripts\release.ps1 -Version $version
Assert-LastExitCode "version synchronization"

$buildStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stageRoot = Join-Path ([System.IO.Path]::GetTempPath()) "SHIM_Portable_${version}_${PID}_$([guid]::NewGuid().ToString('N').Substring(0, 8))"
$stageDist = Join-Path $stageRoot "dist"
$stageWork = Join-Path $stageRoot "build"
$packagePath = Join-Path $stageDist "SHIM_Portable"
$stageZip = Join-Path $stageRoot "SHIM_Portable_v${version}_${buildStamp}.zip"
$publishRoot = Join-Path $ProjectRoot "dist"
$publishPath = Join-Path $publishRoot "SHIM_Portable_v${version}_${buildStamp}.zip"
New-Item -ItemType Directory -Path $publishRoot -Force | Out-Null

if (Test-Path $publishPath) {
    throw "Portable publish path already exists: $publishPath"
}

New-Item -ItemType Directory -Path $stageDist, $stageWork -Force | Out-Null

try {
    Write-Host "[3/4] Run PyInstaller build in local staging directory"
    pyinstaller `
      --noconfirm `
      --clean `
      --name SHIM_Portable `
      --icon "src/static/favicon.ico" `
      --paths "." `
      --collect-submodules src.app `
      --collect-submodules holidays `
      --collect-data holidays `
      --collect-data tzdata `
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
      --distpath $stageDist `
      --workpath $stageWork `
      portable/shim_portable.py
    Assert-LastExitCode "PyInstaller build"

    Write-Host "[4/4] Assemble, verify, and publish immutable ZIP"
    Copy-Item portable\stop_portable.bat (Join-Path $packagePath "stop_portable.bat") -Force
    Copy-Item portable\README_PORTABLE.md (Join-Path $packagePath "README_PORTABLE.md") -Force
    New-Item -ItemType Directory -Path (Join-Path $packagePath "data") -Force | Out-Null

    if (-not (Test-Path (Join-Path $packagePath "SHIM_Portable.exe"))) {
        throw "Portable executable is missing from staged package."
    }

    Compress-Archive -Path (Join-Path $packagePath "*") -DestinationPath $stageZip -CompressionLevel Optimal

    $archive = [System.IO.Compression.ZipFile]::OpenRead($stageZip)
    try {
        $entries = @($archive.Entries | ForEach-Object { $_.FullName })
        if ($entries -notcontains "SHIM_Portable.exe") {
            throw "Portable ZIP does not contain SHIM_Portable.exe."
        }
        $forbidden = @($entries | Where-Object { $_ -match '(^|/)(secret\.key|[^/]+\.(db|db-wal|db-shm|bak))$' })
        if ($forbidden.Count -gt 0) {
            throw "Portable ZIP contains runtime data: $($forbidden -join ', ')"
        }
    } finally {
        $archive.Dispose()
    }

    Copy-Item -LiteralPath $stageZip -Destination $publishPath
    $sourceHash = (Get-FileHash $stageZip -Algorithm SHA256).Hash
    $publishedHash = (Get-FileHash $publishPath -Algorithm SHA256).Hash
    if ($sourceHash -ne $publishedHash) {
        throw "Published ZIP hash mismatch."
    }

    Write-Host "Done: $publishPath"
    Write-Host "SHA256: $publishedHash"
    Write-Host "Copy this ZIP to the target PC and extract the entire archive."
} finally {
    if (Test-Path $stageRoot) {
        Remove-Item -LiteralPath $stageRoot -Recurse -Force
    }
}
