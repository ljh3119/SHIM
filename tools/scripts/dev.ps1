$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $ProjectRoot

Write-Host "[SHIM] Tailwind CSS watch + FastAPI dev server start"
Write-Host "[SHIM] project_root=$ProjectRoot"

$tailwind = Start-Process -FilePath "npx.cmd" `
    -ArgumentList @(
        "tailwindcss",
        "-i", "./src/static/css/app.css",
        "-o", "./src/static/css/tailwind.css",
        "--watch"
    ) `
    -PassThru `
    -NoNewWindow

try {
    python -m uvicorn src.app.main:app --host 0.0.0.0 --port 8080 --reload --reload-dir src
}
finally {
    if ($tailwind -and -not $tailwind.HasExited) {
        Stop-Process -Id $tailwind.Id -Force
    }

    Write-Host "[SHIM] Dev server shutdown complete (prompt returned)"
}
