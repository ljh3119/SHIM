param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version,

    [switch]$BuildImage,
    [switch]$RunChecks,
    [switch]$GitRelease
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

function Assert-LastExitCode([string]$CommandName) {
    if ($LASTEXITCODE -ne 0) {
        throw "$CommandName failed (exit code: $LASTEXITCODE)."
    }
}

function Sync-DocVersionPatterns([string]$Path) {
    $content = Read-Text $Path
    $content = [regex]::Replace($content, 'shim:[0-9]+\.[0-9]+\.[0-9]+', "shim:$Version")
    $content = [regex]::Replace($content, '(release\.ps1\s+-Version\s+)[0-9]+\.[0-9]+\.[0-9]+', ('${1}' + $Version))
    Write-Text $Path $content
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

# 1-1) package-lock.json root package versions
Replace-OrFail (Join-Path $ProjectRoot "package-lock.json") '(?s)^(\{\s*"name":\s*"shim",\s*"version":\s*")[0-9]+\.[0-9]+\.[0-9]+' ('${1}' + $Version)
Replace-OrFail (Join-Path $ProjectRoot "package-lock.json") '(?s)("packages":\s*\{\s*"":\s*\{\s*"name":\s*"shim",\s*"version":\s*")[0-9]+\.[0-9]+\.[0-9]+' ('${1}' + $Version)

# 2) src/app/constants.py application version
Replace-OrFail (Join-Path $ProjectRoot "src\app\constants.py") 'APP_VERSION\s*=\s*"[0-9]+\.[0-9]+\.[0-9]+"' "APP_VERSION = `"$Version`""

# 3) compose default image tags
Replace-OrFail (Join-Path $ProjectRoot "infra\docker\docker-compose.yml") 'image:\s*\$\{SHIM_IMAGE:-shim:[0-9]+\.[0-9]+\.[0-9]+\}' "image: `${SHIM_IMAGE:-shim:$Version}"
Replace-OrFail (Join-Path $ProjectRoot "infra\docker\docker-compose.dev.yml") 'image:\s*\$\{SHIM_IMAGE:-shim:[0-9]+\.[0-9]+\.[0-9]+\}' "image: `${SHIM_IMAGE:-shim:$Version}"
Replace-OrFail (Join-Path $ProjectRoot "infra\docker\docker-compose.test.yml") 'image:\s*\$\{SHIM_IMAGE:-shim:[0-9]+\.[0-9]+\.[0-9]+\}' "image: `${SHIM_IMAGE:-shim:$Version}"

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

# 8) current deployment guides: Docker tags and release command examples
$quickStartDocPath = (Get-ChildItem (Join-Path $ProjectRoot "docs") -Filter "1-1_*.md" | Select-Object -First 1).FullName
Sync-DocVersionPatterns (Join-Path $ProjectRoot "README.md")
Sync-DocVersionPatterns $quickStartDocPath
Sync-DocVersionPatterns $maintenanceDocPath
Sync-DocVersionPatterns (Join-Path $ProjectRoot "portable\README_PORTABLE.md")
Write-Host "[release] Version sync complete."

if ($RunChecks -or $BuildImage) {
    Write-Host "[release] Building Tailwind CSS before checks and packaging"
    npm run build:css
    Assert-LastExitCode "npm run build:css"
    $cssPath = "src\static\css\tailwind.css"
    if (-not (Test-Path $cssPath)) {
        throw "Tailwind CSS output file does not exist: $cssPath"
    }
    $cssFile = Get-Item $cssPath
    if ($cssFile.Length -eq 0) {
        throw "Tailwind CSS output file is 0 bytes: $cssPath"
    }
    Write-Host "[release] Tailwind CSS output verified: $cssPath ($($cssFile.Length) bytes)"
}

if ($RunChecks) {
    Write-Host "[release] Running checks: compile, compose config, version/docs sync, release tests"
    python -m compileall src\app tools\scripts
    Assert-LastExitCode "python compileall"
    docker compose -f infra/docker/docker-compose.yml config | Out-Null
    Assert-LastExitCode "docker compose production config"
    docker compose -f infra/docker/docker-compose.dev.yml config | Out-Null
    Assert-LastExitCode "docker compose development config"
    docker compose -f infra/docker/docker-compose.test.yml config | Out-Null
    Assert-LastExitCode "docker compose test config"
    & "$PSScriptRoot\verify_version_sync.ps1"
    Assert-LastExitCode "verify_version_sync.ps1"
    python tools/scripts/run_tests.py release
    Assert-LastExitCode "release test suite"
    Write-Host "[release] Checks passed."
}

if ($BuildImage) {
    Write-Host "[release] Building docker image tags: shim:$Version, shim:latest"
    docker build -f infra/docker/Dockerfile -t "shim:$Version" -t "shim:latest" .
    Assert-LastExitCode "docker build"
}

if ($GitRelease) {
    Write-Host "[release] Running Git release automation..."
    if (Test-Path "scratch\security_checker.py") {
        Write-Host "[release] Running security checks..."
        python scratch\security_checker.py
        if ($LASTEXITCODE -ne 0) {
            throw "Security check failed. Release aborted to prevent credential leak."
        }
    }
    
    Write-Host "[release] Git staging and committing version changes..."
    git add .
    git commit -m "release: v$Version"
    
    Write-Host "[release] Creating Git tag v$Version..."
    git tag -f "v$Version" -m "Release v$Version"
    
    Write-Host "[release] Pushing main branch and tag v$Version to origin..."
    git push origin main
    git push origin "v$Version"
    Write-Host "[release] Git release and tagging completed successfully."
}

Write-Host "[release] Done."
