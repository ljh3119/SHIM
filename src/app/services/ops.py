from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3


def create_sqlite_backup(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{db_path.stem}_{stamp}.bak"
    
    # SQLite WAL 모드에 대응하는 정합성 보장 핫 백업 API 사용
    src_conn = sqlite3.connect(db_path)
    dest_conn = sqlite3.connect(backup_path)
    try:
        src_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        src_conn.close()
        
    return backup_path
