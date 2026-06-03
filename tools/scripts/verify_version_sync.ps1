# Verifies that package.json "version" matches runtime files and key docs.
# Single source of truth: package.json (same as release.ps1).
# Exit 0 = OK, exit 1 = mismatch.

$ErrorActionPreference = "Stop"

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

$errs = [System.Collections.Generic.List[string]]::new()

function Add-Err([string]$Message) {
    [void]$errs.Add($Message)
}

# Code / config (must match release.ps1 targets)
$constantsPath = Join-Path $ProjectRoot "src\app\constants.py"
$constants = Read-Text $constantsPath
$appVerNeedle = 'APP_VERSION = "' + $ver + '"'
if ($constants.IndexOf($appVerNeedle, [StringComparison]::Ordinal) -lt 0) {
    Add-Err "src/app/constants.py: APP_VERSION must equal package.json ($ver)."
}

$basePath = Join-Path $ProjectRoot "src\templates\base.html"
$base = Read-Text $basePath
$defaultVer = "default('$ver')"
$matches = [regex]::Matches($base, [regex]::Escape($defaultVer))
if ($matches.Count -lt 2) {
    Add-Err "src/templates/base.html: need 2x $defaultVer for app_version (found $($matches.Count))."
}

foreach ($rel in @("infra\docker\docker-compose.yml", "infra\docker\docker-compose.dev.yml")) {
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
