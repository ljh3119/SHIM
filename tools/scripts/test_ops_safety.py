from __future__ import annotations

import os
import sys
import tempfile
from datetime import timedelta, timezone, datetime
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class FailingQuerySession:
    def query(self, *_args, **_kwargs):
        raise RuntimeError("forced cleanup query failure")

    def rollback(self):
        pass

    def close(self):
        pass


class FailingCommitSession:
    def __init__(self, session):
        self._session = session

    def query(self, *args, **kwargs):
        return self._session.query(*args, **kwargs)

    def commit(self):
        raise RuntimeError("forced metrics commit failure")

    def rollback(self):
        self._session.rollback()

    def close(self):
        self._session.close()


def main() -> int:
    original_data_dir = os.environ.get("SHIM_DATA_DIR")
    original_secret = os.environ.get("SHIM_SECRET_KEY")

    with tempfile.TemporaryDirectory(prefix="shim_ops_test_") as temp_dir:
        os.environ["SHIM_DATA_DIR"] = temp_dir
        os.environ.pop("SHIM_SECRET_KEY", None)

        from src.app import auth, database, models
        from src.app.services import ops

        database.Base.metadata.create_all(bind=database.engine)
        db = database.SessionLocal()
        try:
            settings = models.SystemSettings()
            user = models.Users(
                user_id="ops_user",
                user_name="ops_user",
                password=auth.get_password_hash("0000"),
                role="STAFF",
            )
            db.add_all([settings, user])
            db.commit()

            old_notification = models.Notifications(
                user_id=user.user_id,
                message="old",
                created_at=datetime.now(timezone.utc) - timedelta(days=31),
            )
            db.add(old_notification)
            db.commit()

            cleanup_success, deleted = ops.cleanup_old_notifications()
            assert cleanup_success is True
            assert deleted == 1
            db.expire_all()
            settings = db.query(models.SystemSettings).first()
            assert settings.last_cleanup_time is not None

            previous_cleanup = datetime.now(timezone.utc) - timedelta(days=2)
            settings.last_cleanup_time = previous_cleanup
            db.commit()
            with patch.object(database, "SessionLocal", return_value=FailingQuerySession()):
                cleanup_success, deleted = ops.cleanup_old_notifications()
            assert cleanup_success is False
            assert deleted == 0
            db.expire_all()
            assert db.query(models.SystemSettings).first().last_cleanup_time == previous_cleanup

            cleanup_session = database.SessionLocal()
            metrics_session = FailingCommitSession(database.SessionLocal())
            session_sequence = iter((cleanup_session, metrics_session))
            with patch.object(database, "SessionLocal", side_effect=lambda: next(session_sequence)):
                cleanup_success, deleted = ops.cleanup_old_notifications()
            assert cleanup_success is False
            assert deleted == 0
            db.expire_all()
            assert db.query(models.SystemSettings).first().last_cleanup_time == previous_cleanup

            backup_dir = database.DB_PATH.parent / "backup"
            first_backup = ops.create_sqlite_backup(database.DB_PATH, backup_dir)
            assert first_backup.exists()
            assert ops._is_sqlite_healthy(first_backup)
            assert not list(backup_dir.glob("*.tmp"))

            before_backups = set(backup_dir.glob("*.bak"))
            with patch.object(ops, "_is_sqlite_healthy", return_value=False):
                try:
                    ops.create_sqlite_backup(database.DB_PATH, backup_dir)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("무결성 검사 실패 백업은 게시하면 안 됩니다.")
            assert set(backup_dir.glob("*.bak")) == before_backups
            assert not list(backup_dir.glob("*.tmp"))

            before_backups = set(backup_dir.glob("*.bak"))
            with patch.object(ops.os, "replace", side_effect=OSError("forced replace failure")):
                try:
                    ops.create_sqlite_backup(database.DB_PATH, backup_dir)
                except OSError:
                    pass
                else:
                    raise AssertionError("원자 교체 실패는 호출자에게 전달해야 합니다.")
            assert set(backup_dir.glob("*.bak")) == before_backups
            assert not list(backup_dir.glob("*.tmp"))

            invalid_backup = backup_dir / f"{database.DB_PATH.stem}_invalid.bak"
            invalid_backup.write_bytes(b"not-a-database")
            ops.create_sqlite_backup(database.DB_PATH, backup_dir)
            rotated_backup = ops.run_backup_and_rotate(database.DB_PATH, max_backups=2)
            assert rotated_backup is not None and rotated_backup.exists()
            healthy_backups = ops._healthy_backup_files(database.DB_PATH)
            assert len(healthy_backups) == 2
            assert not invalid_backup.exists()
            assert (backup_dir / f"{invalid_backup.name}.invalid").exists()
            db.expire_all()
            assert db.query(models.SystemSettings).first().last_backup_count == 2

            original_unlink = Path.unlink

            def fail_backup_unlink(path, *args, **kwargs):
                if path.suffix == ".bak":
                    raise PermissionError("forced rotation delete failure")
                return original_unlink(path, *args, **kwargs)

            with patch.object(Path, "unlink", fail_backup_unlink):
                failed_rotation_backup = ops.run_backup_and_rotate(database.DB_PATH, max_backups=1)
            assert failed_rotation_backup is not None
            healthy_after_failure = ops._healthy_backup_files(database.DB_PATH)
            assert len(healthy_after_failure) > 1
            db.expire_all()
            assert db.query(models.SystemSettings).first().last_backup_count == len(healthy_after_failure)

            print("[PASS] OPS-001/002 cleanup and backup safety checks completed.")
            return 0
        finally:
            db.close()
            database.engine.dispose()
            if original_secret is None:
                os.environ.pop("SHIM_SECRET_KEY", None)
            else:
                os.environ["SHIM_SECRET_KEY"] = original_secret
            if original_data_dir is None:
                os.environ.pop("SHIM_DATA_DIR", None)
            else:
                os.environ["SHIM_DATA_DIR"] = original_data_dir


if __name__ == "__main__":
    raise SystemExit(main())
