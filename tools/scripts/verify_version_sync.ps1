# Verifies that package.json "version" matches runtime files and key docs.
# Single source of truth: package.json (same as release.ps1).
# Exit 0 = OK, exit 1 = mismatch.

$ErrorActionPreference = "Stop"
$PythonVerifier = Join-Path $PSScriptRoot "verify_version_sync.py"
$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($PythonCommand) {
    & $PythonCommand.Source $PythonVerifier
    exit $LASTEXITCODE
}

# Python is required by SHIM. Keep the legacy PowerShell checks only as a fallback.


$ProjectRoot = (Get-Item "$PSScriptRoot\..\..").FullName
Set-Location $ProjectRoot

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false, $true)
function Read-Text([string]$Path) {
    $ResolvedPath = (Get-Item $Path).FullName
    return [System.IO.File]::ReadAllText($ResolvedPath, $Utf8NoBom)
}

$packageJsonPath = Join-Path $ProjectRoot "package.json"
$package = (Read-Text $packageJsonPath) | ConvertFrom-Json
$ver = [string]$package.version

$packageLockText = Read-Text (Join-Path $ProjectRoot "package-lock.json")
$errs = [System.Collections.Generic.List[string]]::new()

function Add-Err([string]$Message) {
    [void]$errs.Add($Message)
}

function Verify-DocVersionPatterns([string]$RelPath, [string]$ExpectedVersion) {
    $FullPath = Join-Path $ProjectRoot $RelPath
    if (-not (Test-Path $FullPath)) {
        return
    }
    $Content = Read-Text $FullPath
    
    # 1. shim:X.Y.Z 패턴 검사
    $dockerMatches = [regex]::Matches($Content, 'shim:(\d+\.\d+\.\d+)')
    foreach ($m in $dockerMatches) {
        $foundVer = $m.Groups[1].Value
        if ($foundVer -ne $ExpectedVersion) {
            Add-Err "$RelPath : Found obsolete docker tag 'shim:$foundVer' (expected 'shim:$ExpectedVersion')"
        }
    }
    
    # 2. release.ps1 -Version X.Y.Z 패턴 검사
    $releaseMatches = [regex]::Matches($Content, 'release\.ps1\s+-Version\s+(\d+\.\d+\.\d+)')
    foreach ($m in $releaseMatches) {
        $foundVer = $m.Groups[1].Value
        if ($foundVer -ne $ExpectedVersion) {
            Add-Err "$RelPath : Found obsolete release tool argument '-Version $foundVer' (expected '-Version $ExpectedVersion')"
        }
    }
}

$lockVersion = [regex]::Match($packageLockText, '(?s)^\{\s*"name"\s*:\s*"shim"\s*,\s*"version"\s*:\s*"([0-9]+\.[0-9]+\.[0-9]+)"')
$lockRootVersion = [regex]::Match($packageLockText, '(?s)"packages"\s*:\s*\{\s*""\s*:\s*\{\s*"name"\s*:\s*"shim"\s*,\s*"version"\s*:\s*"([0-9]+\.[0-9]+\.[0-9]+)"')
if (-not $lockVersion.Success -or $lockVersion.Groups[1].Value -ne $ver) {
    Add-Err "package-lock.json: root version must equal package.json ($ver)."
}
if (-not $lockRootVersion.Success -or $lockRootVersion.Groups[1].Value -ne $ver) {
    Add-Err "package-lock.json: root package version must equal package.json ($ver)."
}
# Code / config (must match release.ps1 targets)
$constantsPath = Join-Path $ProjectRoot "src\app\constants.py"
$constants = Read-Text $constantsPath
$appVerNeedle = 'APP_VERSION = "' + $ver + '"'
if ($constants.IndexOf($appVerNeedle, [StringComparison]::Ordinal) -lt 0) {
    Add-Err "src/app/constants.py: APP_VERSION must equal package.json ($ver)."
}


foreach ($rel in @("infra\docker\docker-compose.yml", "infra\docker\docker-compose.dev.yml", "infra\docker\docker-compose.test.yml")) {
    $p = Join-Path $ProjectRoot $rel
    $t = Read-Text $p
    if ($t -notmatch [regex]::Escape("shim:$ver")) {
        Add-Err "$rel : default image must include shim:$ver"
    }
}

# Docs: README is the public/version summary; docs/0_* index has no required version string.
$readmePath = Join-Path $ProjectRoot "README.md"
$readme = Read-Text $readmePath
# README line like "**릴리스 버전:** X.Y.Z" (colon inside bold); ASCII-safe tail match
if ($readme -notmatch ('\*\*[^*]+\*\*\s+' + [regex]::Escape($ver) + '(?:\s|$)')) {
    Add-Err "README.md: bold line then spaces then package.json version ($ver)"
}

$portableReadme = Join-Path $ProjectRoot "portable\README_PORTABLE.md"
if (Test-Path $portableReadme) {
    $pr = Read-Text $portableReadme
    if ($pr.IndexOf("v$ver", [StringComparison]::Ordinal) -lt 0) {
        Add-Err "portable/README_PORTABLE.md: must mention v$ver (e.g. next to date)"
    }
}

$designDoc = (Get-ChildItem (Join-Path $ProjectRoot "docs") -Filter "4-1_*.md" | Select-Object -First 1).FullName
if ($designDoc -and (Test-Path $designDoc)) {
    $dd = Read-Text $designDoc
    if ($dd -notmatch ('\*\*([^*]+)\*\*\s*:?\s*' + [regex]::Escape($ver))) {
        Add-Err "docs/4-1_SHIM_프로젝트_설계서.md: must match package.json version ($ver)"
    }
}

$releaseDoc = (Get-ChildItem (Join-Path $ProjectRoot "docs") -Filter "2-1_*.md" | Select-Object -First 1).FullName
if ($releaseDoc -and (Test-Path $releaseDoc)) {
    $releaseText = Read-Text $releaseDoc
    $latestRelease = [regex]::Match($releaseText, '(?m)^### v([0-9]+\.[0-9]+\.[0-9]+)')
    if (-not $latestRelease.Success -or $latestRelease.Groups[1].Value -ne $ver) {
        Add-Err "docs/2-1_운영_릴리즈_통합_산출물.md: latest release heading must be v$ver."
    }
}
$maintenanceDoc = (Get-ChildItem (Join-Path $ProjectRoot "docs") -Filter "1-2_*.md" | Select-Object -First 1).FullName
if ($maintenanceDoc -and (Test-Path $maintenanceDoc)) {
    $mc = Read-Text $maintenanceDoc
    if ($mc -notmatch ('-Version\s+' + [regex]::Escape($ver))) {
        Add-Err "docs/1-2_백업_복구_유지보수_가이드.md: release command example must match version ($ver)"
    }
}

# 가이드 문서들의 세부 버전 정합성 검사 (Docker 이미지 태그 및 release.ps1 매개변수)
Verify-DocVersionPatterns "README.md" $ver
Verify-DocVersionPatterns "docs\1-1_초심자_구동_가이드.md" $ver
Verify-DocVersionPatterns "docs\1-2_백업_복구_유지보수_가이드.md" $ver
Verify-DocVersionPatterns "portable\README_PORTABLE.md" $ver

if ($errs.Count -gt 0) {
    Write-Host "verify_version_sync: expected version from package.json = $ver" -ForegroundColor Yellow
    foreach ($e in $errs) {
        Write-Host "  - $e" -ForegroundColor Red
    }
    Write-Host "verify_version_sync: FAILED ($($errs.Count) issue(s))" -ForegroundColor Red
    exit 1
}

Write-Host "verify_version_sync: OK (package.json = $ver)"
exit 0
