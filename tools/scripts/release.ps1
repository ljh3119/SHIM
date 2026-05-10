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

# 2) src/app/main.py application version
Replace-OrFail (Join-Path $ProjectRoot "src\app\main.py") 'FastAPI\(title="SHIM", version="[0-9]+\.[0-9]+\.[0-9]+"\)' "FastAPI(title=`"SHIM`", version=`"$Version`")"
Replace-OrFail (Join-Path $ProjectRoot "src\app\main.py") 'templates\.env\.globals\["app_version"\] = "[0-9]+\.[0-9]+\.[0-9]+"' "templates.env.globals[`"app_version`"] = `"$Version`""

# 3) src/templates/base.html default version fallback
Replace-OrFail (Join-Path $ProjectRoot "src\templates\base.html") "default\('[0-9]+\.[0-9]+\.[0-9]+'\)" "default('$Version')"
Replace-OrFail (Join-Path $ProjectRoot "src\templates\base.html") "default\('[0-9]+\.[0-9]+\.[0-9]+'\)" "default('$Version')"

# 4) compose default image tags
Replace-OrFail (Join-Path $ProjectRoot "infra\docker\docker-compose.yml") 'image:\s*\$\{SHIM_IMAGE:-shim:[0-9]+\.[0-9]+\.[0-9]+\}' "image: `${SHIM_IMAGE:-shim:$Version}"
Replace-OrFail (Join-Path $ProjectRoot "infra\docker\docker-compose.dev.yml") 'image:\s*\$\{SHIM_IMAGE:-shim:[0-9]+\.[0-9]+\.[0-9]+\}' "image: `${SHIM_IMAGE:-shim:$Version}"

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
