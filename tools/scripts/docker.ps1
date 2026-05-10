param(
    [Parameter(Mandatory = $false, Position = 0)]
    [ValidateSet("build", "up-prod", "up-dev", "down", "ps", "logs", "restart", "help")]
    [string]$Command = "help"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $ProjectRoot

function Get-AppVersion {
    $packageJsonPath = Join-Path $ProjectRoot "package.json"
    if (-not (Test-Path $packageJsonPath)) {
        throw "package.json not found: $packageJsonPath"
    }
    $package = Get-Content $packageJsonPath -Raw | ConvertFrom-Json
    if (-not $package.version) {
        throw "version field is missing in package.json"
    }
    return [string]$package.version
}

function Show-Help {
    $currentVersion = Get-AppVersion
    Write-Host "SHIM Docker shortcut commands"
    Write-Host ""
    Write-Host "Current app version: $currentVersion"
    Write-Host ""
    Write-Host "Usage:"
    Write-Host "  .\tools\scripts\docker.ps1 <command>"
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  build    : docker image build (shim:$currentVersion and shim:latest)"
    Write-Host "  up-prod  : run prod compose (image-only mode)"
    Write-Host "  up-dev   : run dev compose with --build"
    Write-Host "  down     : stop and remove containers/network"
    Write-Host "  ps       : show compose service status"
    Write-Host "  logs     : show shim service logs (follow)"
    Write-Host "  restart  : restart shim service"
    Write-Host "  help     : print this help"
}

switch ($Command) {
    "build" {
        $version = Get-AppVersion
        docker build -f infra/docker/Dockerfile -t "shim:$version" -t "shim:latest" .
        break
    }
    "up-prod" {
        docker compose -f infra/docker/docker-compose.yml up -d
        break
    }
    "up-dev" {
        docker compose -f infra/docker/docker-compose.dev.yml up -d --build
        break
    }
    "down" {
        docker compose -f infra/docker/docker-compose.yml down
        break
    }
    "ps" {
        docker compose -f infra/docker/docker-compose.yml ps
        break
    }
    "logs" {
        docker compose -f infra/docker/docker-compose.yml logs -f shim
        break
    }
    "restart" {
        docker compose -f infra/docker/docker-compose.yml restart shim
        break
    }
    default {
        Show-Help
        break
    }
}
