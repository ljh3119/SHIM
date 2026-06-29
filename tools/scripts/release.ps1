param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version,

    [switch]$BuildImage,
    [switch]$RunChecks
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $ProjectRoot

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false, $true)

function Read-Text([string]$Path) {
    return [System.IO.File]::ReadAllText($Path, $Utf8NoBom)
}

function Write-Text([string]$Path, [string]$Content) {
    [System.IO.File]::WriteAllText($Path, $Content, $Utf8NoBom)
}

function Replace-OrFail([string]$Path, [string]$Pattern, [string]$Replacement) {
    $content = Read-Text $Path
    if (-not [regex]::IsMatch($content, $Pattern)) {
        throw "Pattern not found in $Path`nPattern: $Pattern"
    }
    $updated = [regex]::Replace($content, $Pattern, $Replacement, 1)
    Write-Text $Path $updated
}

$packageJsonPath = Join-Path $ProjectRoot "package.json"
$package = (Read-Text $packageJsonPath) | ConvertFrom-Json
$currentVersion = [string]$package.version

if ($currentVersion -eq $Version) {
    Write-Host "[release] Version is already $Version (idempotent update)."
} else {
    Write-Host "[release] Version update: $currentVersion -> $Version"
}

# 1) package.json version
Replace-OrFail $packageJsonPath '"version"\s*:\s*"[0-9]+\.[0-9]+\.[0-9]+"' "`"version`": `"$Version`""

# 2) src/app/constants.py application version
Replace-OrFail (Join-Path $ProjectRoot "src\app\constants.py") 'APP_VERSION\s*=\s*"[0-9]+\.[0-9]+\.[0-9]+"' "APP_VERSION = `"$Version`""

# 3) compose default image tags
Replace-OrFail (Join-Path $ProjectRoot "infra\docker\docker-compose.yml") 'image:\s*\$\{SHIM_IMAGE:-shim:[0-9]+\.[0-9]+\.[0-9]+\}' "image: `${SHIM_IMAGE:-shim:$Version}"
Replace-OrFail (Join-Path $ProjectRoot "infra\docker\docker-compose.dev.yml") 'image:\s*\$\{SHIM_IMAGE:-shim:[0-9]+\.[0-9]+\.[0-9]+\}' "image: `${SHIM_IMAGE:-shim:$Version}"

# 4) README.md release version line
Replace-OrFail (Join-Path $ProjectRoot "README.md") '(\*\*[^*]+?\*\*\s*:?\s*)[0-9]+\.[0-9]+\.[0-9]+' ('${1}' + $Version)

# 5) portable/README_PORTABLE.md update date and version
$today = Get-Date -Format "yyyy-MM-dd"
Replace-OrFail (Join-Path $ProjectRoot "portable\README_PORTABLE.md") '(\*\*[^*]+?\*\*\s*:\s*)\d{4}-\d{2}-\d{2}(\s*\(v)[0-9]+\.[0-9]+\.[0-9]+(\))' ('${1}' + $today + '${2}' + $Version + '${3}')

# 6) docs/4-1_SHIM_프로젝트_설계서.md update version and date (using ASCII-safe filter)
$designDocPath = (Get-ChildItem (Join-Path $ProjectRoot "docs") -Filter "4-1_*.md" | Select-Object -First 1).FullName
Replace-OrFail $designDocPath '(\*\*[^*]+?\*\*\s*:?\s*)[0-9]+\.[0-9]+\.[0-9]+' ('${1}' + $Version)
Replace-OrFail $designDocPath '(\*\*[^*]+?\*\*\s*:\s*)\d{4}-\d{2}-\d{2}' ('${1}' + $today)

# 7) docs/1-2_백업_복구_유지보수_가이드.md update version examples and date (using ASCII-safe filter)
$maintenanceDocPath = (Get-ChildItem (Join-Path $ProjectRoot "docs") -Filter "1-2_*.md" | Select-Object -First 1).FullName
Replace-OrFail $maintenanceDocPath '(\(예:\s*`)[0-9]+\.[0-9]+\.[0-9]+' ('${1}' + $Version)
Replace-OrFail $maintenanceDocPath '(-Version\s+)[0-9]+\.[0-9]+\.[0-9]+' ('${1}' + $Version)
Replace-OrFail $maintenanceDocPath '(shim_)[0-9]+\.[0-9]+\.[0-9]+(\.tar\s+shim:)[0-9]+\.[0-9]+\.[0-9]+' ('${1}' + $Version + '${2}' + $Version)
Replace-OrFail $maintenanceDocPath '(\*\*[^*]+?\*\*\s*:\s*)\d{4}-\d{2}-\d{2}' ('${1}' + $today)

Write-Host "[release] Version sync complete."

if ($BuildImage) {
    Write-Host "[release] Building docker image tags: shim:$Version, shim:latest"
    docker build -f infra/docker/Dockerfile -t "shim:$Version" -t "shim:latest" .
}

if ($RunChecks) {
    Write-Host "[release] Running checks: compile, CSS build, compose config, version/docs sync"
    python -m compileall src\app tools\scripts
    npm run build:css
    docker compose -f infra/docker/docker-compose.yml config | Out-Null
    & "$PSScriptRoot\verify_version_sync.ps1"
    if ($LASTEXITCODE -ne 0) { throw "verify_version_sync.ps1 failed (see messages above)" }
    Write-Host "[release] Checks passed."
}

Write-Host "[release] Done."
