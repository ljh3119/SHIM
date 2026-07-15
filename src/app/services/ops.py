from __future__ import annotations

import os
import time
import shutil
import sqlite3
import asyncio
import threading
from datetime import datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from src.app.utils import get_business_now, get_business_timezone
from src.app import models
from src.app.database import DB_PATH

# 전역 백업 스레드 락 도입 (동시 백업 쓰기 방지 및 SQLite 락 충돌 우회)
_backup_lock = threading.Lock()

# Thread-lock-based backup mechanism is used instead of filesystem-based ProcessFileLock.

def create_sqlite_backup(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = get_business_now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"{db_path.stem}_{stamp}.bak"
    temporary_path = backup_dir / f".{backup_path.name}.tmp"
    src_conn = None
    dest_conn = None

    try:
        try:
            src_conn = sqlite3.connect(db_path, timeout=30.0)
            dest_conn = sqlite3.connect(temporary_path, timeout=30.0)
            src_conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
            src_conn.backup(dest_conn, pages=50, sleep=0.02)
        finally:
            if dest_conn is not None:
                dest_conn.close()
            if src_conn is not None:
                src_conn.close()

        if not _is_sqlite_healthy(temporary_path):
            raise RuntimeError("New SQLite backup failed integrity validation.")
        os.replace(temporary_path, backup_path)
        return backup_path
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

def run_backup_and_rotate(db_path: Path, max_backups: int = 5) -> Path | None:
    with _backup_lock:
        backup_dir = db_path.parent / "backup"
        try:
            backup_path = create_sqlite_backup(db_path, backup_dir)
            print(f"[SHIM BACKUP] Successfully created backup: {backup_path}")
        except Exception as e:
            print(f"[SHIM BACKUP ERROR] Failed to create backup: {e}")
            return None

        backup_files = None
        try:
            backup_files = _healthy_backup_files(db_path, isolate_invalid=True)
            while len(backup_files) > max_backups:
                oldest = backup_files[0]
                try:
                    oldest.unlink()
                    backup_files.pop(0)
                    print(f"[SHIM BACKUP ROTATION] Deleted oldest backup file: {oldest}")
                except Exception as rm_err:
                    print(f"[SHIM BACKUP ROTATION ERROR] Failed to delete {oldest}: {rm_err}")
                    break
            backup_files = _healthy_backup_files(db_path)
        except Exception as rot_err:
            print(f"[SHIM BACKUP ROTATION ERROR] Error during rotation: {rot_err}")

        from src.app.database import SessionLocal
        db = SessionLocal()
        try:
            settings = db.query(models.SystemSettings).first()
            if settings:
                settings.last_backup_time = get_business_now()
                if backup_files is not None:
                    settings.last_backup_count = len(backup_files)
                settings.last_db_size_kb = int(os.path.getsize(db_path) // 1024)
                db.commit()
        except Exception as db_err:
            db.rollback()
            print(f"[SHIM BACKUP METRICS ERROR] Failed to update backup metrics: {db_err}")
        finally:
            db.close()

        return backup_path

async def daily_backup_scheduler(db_path: Path):
    print("[SHIM BACKUP] Daily backup scheduler started.")
    while True:
        try:
            backup_files = _healthy_backup_files(db_path)
            now_ts = datetime.now(timezone.utc).timestamp()
            has_recent_backup = any(
                now_ts - backup.stat().st_mtime < 24 * 3600
                for backup in backup_files
            )
            
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

def _is_sqlite_healthy(db_path: Path) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(str(db_path.resolve()), timeout=10.0)
        conn.execute("PRAGMA query_only = ON;")
        result = conn.execute("PRAGMA quick_check;").fetchall()
        return bool(result) and result[0][0] == "ok"
    except (OSError, sqlite3.DatabaseError):
        return False
    finally:
        if conn is not None:
            conn.close()


def _healthy_backup_files(db_path: Path, *, isolate_invalid: bool = False) -> list[Path]:
    backup_dir = db_path.parent / "backup"
    if not backup_dir.exists():
        return []

    healthy = []
    for backup_path in backup_dir.glob(f"{db_path.stem}_*.bak"):
        if _is_sqlite_healthy(backup_path):
            healthy.append(backup_path)
        elif isolate_invalid:
            invalid_path = backup_path.with_name(f"{backup_path.name}.invalid")
            try:
                backup_path.replace(invalid_path)
                print(f"[SHIM BACKUP] Isolated invalid backup: {invalid_path}")
            except Exception as invalid_err:
                print(f"[SHIM BACKUP ERROR] Failed to isolate {backup_path}: {invalid_err}")

    healthy.sort(key=lambda path: path.stat().st_mtime)
    return healthy


def _is_corruption_error(error: sqlite3.OperationalError) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in ("malformed", "not a database", "file is encrypted"))

def verify_and_recover_db(db_path: Path):
    if not db_path.exists():
        return

    print(f"[SHIM DATABASE] Verifying integrity of database: {db_path}")
    is_corrupt = False
    conn = None
    
    # NAS 등 느린 네트워크 스토리지의 파일 락 해제 대기를 위해 최대 5회 재시도
    for attempt in range(5):
        try:
            conn = sqlite3.connect(db_path, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute("PRAGMA quick_check;")
            res = cursor.fetchall()
            if not res or res[0][0] != "ok":
                print(f"[SHIM DATABASE] quick_check failed: {res}")
                is_corrupt = True
            break
        except sqlite3.OperationalError as oe:
            err_msg = str(oe).lower()
            if "locked" in err_msg or "busy" in err_msg:
                print(f"[SHIM DATABASE WARNING] Database is busy/locked (attempt {attempt + 1}/5). Retrying in 1s...")
                time.sleep(1.0)
                if attempt == 4:
                    # 락 해제가 지연되는 경우 파일 격리(삭제)를 수행하지 않고 예외를 던져 안전하게 재기동되도록 조치
                    raise oe
                continue
            if _is_corruption_error(oe):
                print(f"[SHIM DATABASE CORRUPT] Corruption error during quick_check: {oe}")
                is_corrupt = True
                break
            raise RuntimeError(f"Database access failed without confirmed corruption: {oe}") from oe
        except sqlite3.DatabaseError as de:
            print(f"[SHIM DATABASE CORRUPT] DatabaseError during quick_check (corruption suspected): {de}")
            is_corrupt = True
            break
        except Exception as e:
            raise RuntimeError(f"Database integrity check could not complete: {e}") from e
        finally:
            if conn:
                conn.close()
                conn = None

    if is_corrupt:
        print("[SHIM DATABASE CORRUPT] Database corruption detected!")
        backup_dir = db_path.parent / "backup"
        backup_files = sorted(
            backup_dir.glob(f"{db_path.stem}_*.bak") if backup_dir.exists() else [],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        latest_backup = next((path for path in backup_files if _is_sqlite_healthy(path)), None)
        if latest_backup is None:
            raise RuntimeError("Database corruption confirmed, but no valid backup is available. Original database was preserved.")
        print(f"[SHIM DATABASE] Validated recovery backup: {latest_backup}")

        # 1. Isolate corrupted DB file
        stamp = get_business_now().strftime("%Y%m%d_%H%M%S")
        corrupted_path = db_path.parent / f"{db_path.name}_corrupted_{stamp}"
        try:
            shutil.move(str(db_path), str(corrupted_path))
            print(f"[SHIM DATABASE] Isolated corrupted DB to {corrupted_path}")
        except Exception as move_err:
            raise RuntimeError(f"Failed to isolate corrupted database: {move_err}") from move_err

        # Also rename WAL and SHM files if they exist, to prevent conflicts
        for suffix in ("-wal", "-shm"):
            extra_file = db_path.parent / f"{db_path.name}{suffix}"
            if extra_file.exists():
                try:
                    shutil.move(str(extra_file), db_path.parent / f"{extra_file.name}_corrupted_{stamp}")
                except Exception as extra_err:
                    print(f"[SHIM DATABASE ERROR] Failed to move {suffix} file: {extra_err}")

        # 2. Restore only from a validated backup, using an atomic replacement.
        restore_tmp = db_path.parent / f".{db_path.name}.restore-{stamp}.tmp"
        print(f"[SHIM DATABASE] Restoring from validated backup: {latest_backup}")
        try:
            shutil.copy2(latest_backup, restore_tmp)
            if not _is_sqlite_healthy(restore_tmp):
                raise RuntimeError("Copied backup failed its integrity check.")
            os.replace(restore_tmp, db_path)
            print("[SHIM DATABASE] Restore completed successfully. Server will proceed to boot.")
        except Exception as restore_err:
            if restore_tmp.exists():
                restore_tmp.unlink()
            if not db_path.exists() and corrupted_path.exists():
                shutil.copy2(corrupted_path, db_path)
            raise RuntimeError(f"Failed to restore validated backup: {restore_err}") from restore_err


def cleanup_old_notifications() -> tuple[bool, int]:
    """30일이 경과한 알림을 청크(100건) 단위로 삭제하고 성공 여부·삭제 건수를 반환합니다."""
    from src.app.database import SessionLocal

    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    total_deleted = 0
    cleanup_succeeded = True

    while True:
        db = SessionLocal()
        try:
            targets = db.query(models.Notifications.id).filter(
                models.Notifications.created_at < thirty_days_ago
            ).limit(100).all()
            if not targets:
                break

            target_ids = [target[0] for target in targets]
            deleted_count = db.query(models.Notifications).filter(
                models.Notifications.id.in_(target_ids)
            ).delete(synchronize_session=False)
            db.commit()
            total_deleted += deleted_count
            print(f"[SHIM NOTIFICATION CLEANUP] Deleted {deleted_count} notifications chunk. Total: {total_deleted}")
            if deleted_count < 100:
                break
        except Exception as error:
            db.rollback()
            cleanup_succeeded = False
            print(f"[SHIM NOTIFICATION CLEANUP ERROR] Failed after deleting {total_deleted}: {error}")
            break
        finally:
            db.close()

        time.sleep(0.1)

    if not cleanup_succeeded:
        return False, total_deleted

    metrics_succeeded = True
    db = SessionLocal()
    try:
        settings = db.query(models.SystemSettings).first()
        if settings:
            settings.last_cleanup_time = get_business_now()
            if DB_PATH.exists():
                settings.last_db_size_kb = int(os.path.getsize(DB_PATH) // 1024)
            db.commit()
    except Exception as db_err:
        db.rollback()
        metrics_succeeded = False
        print(f"[SHIM CLEANUP METRICS ERROR] Cleanup succeeded but metrics failed: {db_err}")
    finally:
        db.close()

    return metrics_succeeded, total_deleted


def get_next_notification_cleanup_run(now_utc: datetime | None = None) -> datetime:
    now_utc = now_utc or datetime.now(timezone.utc)
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise ValueError("now_utc must be timezone-aware")

    now_utc = now_utc.astimezone(timezone.utc)
    business_tz = get_business_timezone()
    target_date = now_utc.astimezone(business_tz).date()
    while True:
        # fold=0 selects the first occurrence when the wall time is duplicated.
        target_local = datetime.combine(target_date, datetime_time(2), tzinfo=business_tz).replace(fold=0)
        target_utc = target_local.astimezone(timezone.utc)
        # A nonexistent 02:00 normalizes through UTC to the first valid local instant after the gap.
        target_local = target_utc.astimezone(business_tz)
        target_utc = target_local.astimezone(timezone.utc)
        if target_utc > now_utc:
            return target_utc
        target_date += timedelta(days=1)


async def notification_cleanup_scheduler():
    print("[SHIM NOTIFICATION CLEANUP] Scheduler started.")
    # 기동 시 즉시 1회 청소 수행하여 사각지대 해소
    from fastapi.concurrency import run_in_threadpool
    await run_in_threadpool(cleanup_old_notifications)

    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            target_utc = get_next_notification_cleanup_run(now_utc)
            sleep_seconds = (target_utc - now_utc).total_seconds()
            target_local = target_utc.astimezone(get_business_timezone())
            print(f"[SHIM NOTIFICATION CLEANUP] Next cleanup scheduled at {target_local} (in {sleep_seconds:.1f}s)")
            await asyncio.sleep(sleep_seconds)

            await run_in_threadpool(cleanup_old_notifications)
        except asyncio.CancelledError:
            print("[SHIM NOTIFICATION CLEANUP] Scheduler cancelled. Exiting cleanly.")
            raise
        except Exception as e:
            print(f"[SHIM NOTIFICATION CLEANUP ERROR] Error in scheduler: {e}")
            await asyncio.sleep(3600)


def update_system_metrics_in_db(db):
    """현재 DB 파일 용량(KB) 및 백업본 개수를 구하여 system_settings에 영속 업데이트합니다.
    기동 시 혹은 스케줄러 성공 시 호출되며, I/O 에러 발생 시 기동 Fatal Crash 방지를 위해 예외를 캡슐화 처리합니다.
    """
    try:
        if not DB_PATH.exists():
            return

        # 1. 파일 크기 구하기 및 KB 단위로 캐스팅
        size_bytes = os.path.getsize(DB_PATH)
        size_kb = int(size_bytes // 1024)

        # 정상 백업만 운영 메트릭에 포함합니다.
        backup_count = len(_healthy_backup_files(DB_PATH))

        # 3. DB 업데이트
        settings = db.query(models.SystemSettings).first()
        if settings:
            settings.last_db_size_kb = size_kb
            settings.last_backup_count = backup_count
            db.commit()
    except Exception as e:
        if db:
            db.rollback()
        import logging
        logging.getLogger("shim.ops").error(
            f"Failed to update system metrics in DB: {e}",
            exc_info=True
        )


