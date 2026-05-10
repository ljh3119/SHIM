from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil


def create_sqlite_backup(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{db_path.stem}_{stamp}.bak"
    shutil.copy2(db_path, backup_path)
    return backup_path
