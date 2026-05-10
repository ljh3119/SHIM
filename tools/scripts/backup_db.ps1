param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
)

Set-Location $ProjectRoot
$env:PYTHONPATH = $ProjectRoot
python -c "from pathlib import Path; from src.app.database import DB_PATH; from src.app.services.ops import create_sqlite_backup; p=create_sqlite_backup(DB_PATH, DB_PATH.parent / 'backup'); print(f'backup_created={p}')"
