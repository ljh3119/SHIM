param(
    [Parameter(Mandatory = $false)]
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $ProjectRoot

function Get-AvailablePort {
    param(
        [int]$StartPort = 9090,
        [int]$MaxPort = 9290
    )
    for ($p = $StartPort; $p -le $MaxPort; $p++) {
        try {
            $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, $p)
            $listener.Start()
            $listener.Stop()
            return $p
        } catch {
            # Port is busy or excluded
        }
    }
    throw "No available port found in range $StartPort - $MaxPort"
}

if ($Port -gt 0) {
    $TargetPort = $Port
} else {
    $TargetPort = Get-AvailablePort -StartPort 9090
}

Write-Host "[SHIM] Tailwind CSS watch + FastAPI dev server start"
Write-Host "[SHIM] project_root=$ProjectRoot"
Write-Host "[SHIM] Target port resolved: $TargetPort"
Write-Host "[SHIM] Access the app at: http://localhost:$TargetPort"

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
    python -m uvicorn src.app.main:app --host 0.0.0.0 --port $TargetPort --reload --reload-dir src
}
finally {
    if ($tailwind -and -not $tailwind.HasExited) {
        Stop-Process -Id $tailwind.Id -Force
    }

    Write-Host "[SHIM] Dev server shutdown complete (prompt returned)"
}

