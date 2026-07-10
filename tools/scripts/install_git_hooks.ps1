$ErrorActionPreference = "Stop"

$ProjectRoot = (Get-Item "$PSScriptRoot\..\..").FullName
git -C $ProjectRoot config core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Git hooks installed from .githooks"
exit 0
