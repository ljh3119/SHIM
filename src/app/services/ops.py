from __future__ import annotations

import os
import shutil
import sqlite3
import asyncio
import threading
from datetime import datetime
from pathlib import Path

# 전역 백업 스레드 락 도입 (동시 백업 쓰기 방지 및 SQLite 락 충돌 우회)
_backup_lock = threading.Lock()

def create_sqlite_backup(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    # 동시성 백업 시 파일명 충돌을 원천 차단하기 위해 마이크로초(%f) 포맷을 추가합니다.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"{db_path.stem}_{stamp}.bak"
    
    # timeout 지정을 통해 database is locked 회귀 예방
    src_conn = sqlite3.connect(db_path, timeout=30.0)
    dest_conn = sqlite3.connect(backup_path, timeout=30.0)
    try:
        # 1. 백업 복제 개시 전, 원본 DB의 WAL 변경 정보 본체 파일에 병합
        src_conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
        
        # 2. 안전한 점진적 증분 백업 실행 (pages=50 단위로 백업하며 매 스텝 0.02초씩 sleep을 취해 타 쓰기 작업에 락 양보)
        src_conn.backup(dest_conn, pages=50, sleep=0.02)
    finally:
        dest_conn.close()
        src_conn.close()
        
    return backup_path

def run_backup_and_rotate(db_path: Path, max_backups: int = 5) -> Path | None:
    # 스레드 락을 사용해 백업 작업이 병렬로 실행되어 파일 쓰기 충돌이 일어나는 것을 방지합니다.
    with _backup_lock:
        backup_dir = db_path.parent / "backup"
        try:
            backup_path = create_sqlite_backup(db_path, backup_dir)
            print(f"[SHIM BACKUP] Successfully created backup: {backup_path}")
        except Exception as e:
            print(f"[SHIM BACKUP ERROR] Failed to create backup: {e}")
            return None
            
        try:
            backup_files = list(backup_dir.glob(f"{db_path.stem}_*.bak"))
            # Sort by modification time (oldest first)
            backup_files.sort(key=lambda p: p.stat().st_mtime)
            
            while len(backup_files) > max_backups:
                oldest = backup_files.pop(0)
                try:
                    os.remove(oldest)
                    print(f"[SHIM BACKUP ROTATION] Deleted oldest backup file: {oldest}")
                except Exception as rm_err:
                    print(f"[SHIM BACKUP ROTATION ERROR] Failed to delete {oldest}: {rm_err}")
        except Exception as rot_err:
            print(f"[SHIM BACKUP ROTATION ERROR] Error during rotation: {rot_err}")
            
        return backup_path

async def daily_backup_scheduler(db_path: Path):
    print("[SHIM BACKUP] Daily backup scheduler started.")
    while True:
        try:
            backup_dir = db_path.parent / "backup"
            has_recent_backup = False
            if backup_dir.exists():
                backup_files = list(backup_dir.glob(f"{db_path.stem}_*.bak"))
                now_ts = datetime.now().timestamp()
                for bf in backup_files:
                    if now_ts - bf.stat().st_mtime < 24 * 3600:
                        has_recent_backup = True
                        break
            
            if not has_recent_backup:
                print("[SHIM BACKUP] No recent backup found in last 24 hours. Running scheduled backup...")
                from fastapi.concurrency import run_in_threadpool
                await run_in_threadpool(run_backup_and_rotate, db_path)
        except asyncio.CancelledError:
            print("[SHIM BACKUP] Daily backup scheduler task cancelled. Exiting cleanly.")
            raise
        except Exception as e:
            print(f"[SHIM BACKUP ERROR] Error in daily backup scheduler: {e}")
            
        # Check every hour
        await asyncio.sleep(3600)

def verify_and_recover_db(db_path: Path):
    if not db_path.exists():
        return

    print(f"[SHIM DATABASE] Verifying integrity of database: {db_path}")
    is_corrupt = False
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        cursor = conn.cursor()
        cursor.execute("PRAGMA quick_check;")
        res = cursor.fetchall()
        if not res or res[0][0] != "ok":
            print(f"[SHIM DATABASE] quick_check failed: {res}")
            is_corrupt = True
    except Exception as e:
        print(f"[SHIM DATABASE] quick_check error: {e}")
        is_corrupt = True
    finally:
        if conn:
            conn.close()

    if is_corrupt:
        print("[SHIM DATABASE CORRUPT] Database corruption detected!")
        # 1. Isolate corrupted DB file
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        corrupted_path = db_path.parent / f"{db_path.name}_corrupted_{stamp}"
        try:
            shutil.move(str(db_path), str(corrupted_path))
            print(f"[SHIM DATABASE] Isolated corrupted DB to {corrupted_path}")
        except Exception as move_err:
            print(f"[SHIM DATABASE ERROR] Failed to isolate corrupted DB: {move_err}")
            return

        # Also rename WAL and SHM files if they exist, to prevent conflicts
        for suffix in ("-wal", "-shm"):
            extra_file = db_path.parent / f"{db_path.name}{suffix}"
            if extra_file.exists():
                try:
                    shutil.move(str(extra_file), db_path.parent / f"{extra_file.name}_corrupted_{stamp}")
                except Exception as extra_err:
                    print(f"[SHIM DATABASE ERROR] Failed to move {suffix} file: {extra_err}")

        # 2. Restore from the most recent backup
        backup_dir = db_path.parent / "backup"
        if backup_dir.exists():
            backup_files = list(backup_dir.glob(f"{db_path.stem}_*.bak"))
            if backup_files:
                backup_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                latest_backup = backup_files[0]
                print(f"[SHIM DATABASE] Restoring from latest backup: {latest_backup}")
                try:
                    shutil.copy(str(latest_backup), str(db_path))
                    print("[SHIM DATABASE] Restore completed successfully. Server will proceed to boot.")
                except Exception as restore_err:
                    print(f"[SHIM DATABASE ERROR] Failed to copy backup: {restore_err}")
            else:
                print("[SHIM DATABASE WARNING] No backup files found in backup directory. Initializing empty database.")
        else:
            print("[SHIM DATABASE WARNING] Backup directory does not exist. Initializing empty database.")
