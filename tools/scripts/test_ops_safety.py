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
        from src.app.migrations import run_all_migrations
        from src.app.key_material import resolve_key_fingerprint
        run_all_migrations(database.engine)
        db = database.SessionLocal()
        try:
            settings = models.SystemSettings(key_hash_snapshot=resolve_key_fingerprint(database.DB_PATH.parent))
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

            # OPS-002: 일간 백업 스케줄러 24시간 최근 호환 백업 판정 검증
            import asyncio
            import sqlite3
            from unittest.mock import MagicMock

            base_backup_dir = Path(temp_dir) / "template_backups"
            base_backup_dir.mkdir(parents=True, exist_ok=True)
            proto_compatible = base_backup_dir / "proto_compat.bak"
            with sqlite3.connect(database.DB_PATH) as src, sqlite3.connect(proto_compatible) as dest:
                src.backup(dest)

            proto_incompatible = base_backup_dir / "proto_incompat.bak"
            with sqlite3.connect(proto_compatible) as src, sqlite3.connect(proto_incompatible) as dest:
                src.backup(dest)
                dest.execute(
                    "INSERT INTO system_settings (id, is_approval_required, time_granularity_minutes, "
                    "work_start_minute, work_end_minute, product_display_name, product_nav_short, "
                    "brand_initial, team_calendar_visible, company_calendar_visible) "
                    "VALUES (2, 0, 60, 540, 1080, 'S', '', 'S', 1, 0)"
                )
                dest.commit()

            fingerprint = resolve_key_fingerprint(database.DB_PATH.parent)
            assert ops._validate_recovery_candidate(proto_compatible, fingerprint)[0] is True
            assert ops._validate_recovery_candidate(proto_incompatible, fingerprint)[0] is False

            fixed_now_ts = 1_794_484_800.0
            fixed_now = datetime.fromtimestamp(fixed_now_ts, tz=timezone.utc)

            class FixedDatetime(datetime):
                @classmethod
                def now(cls, tz=None):
                    if tz is not None:
                        return fixed_now.astimezone(tz)
                    return fixed_now

            scenarios = [
                ("백업 없음", [], True),
                ("1시간 전 비호환본만", [("incompat", 3600)], True),
                ("최신 비호환(1h)+2시간 전 호환", [("incompat", 3600), ("compat", 7200)], False),
                ("호환본 age 0", [("compat", 0)], False),
                ("24시간 직전(24h - 1s)", [("compat", 24 * 3600 - 1)], False),
                ("정확히 24시간", [("compat", 24 * 3600)], True),
                ("미래 1초(-1s)", [("compat", -1)], True),
            ]

            async def run_scheduler_test(case_db: Path, expect_create: bool):
                real_sleep = asyncio.sleep

                async def mock_sleep(seconds):
                    if seconds == 3600:
                        raise asyncio.CancelledError()
                    return await real_sleep(seconds)

                mock_rotate = MagicMock(return_value=case_db.parent / "backup" / "new.bak")

                with patch.object(ops, "datetime", FixedDatetime), \
                     patch.object(ops.asyncio, "sleep", side_effect=mock_sleep), \
                     patch.object(ops, "run_backup_and_rotate", mock_rotate):
                    try:
                        await ops.daily_backup_scheduler(case_db)
                    except asyncio.CancelledError:
                        pass

                assert mock_rotate.called is expect_create, (
                    f"Expected create={expect_create}, but got called={mock_rotate.called}"
                )

            for idx, (name, file_specs, expect_create) in enumerate(scenarios):
                case_dir = Path(temp_dir) / f"sched_case_{idx}"
                case_backup_dir = case_dir / "backup"
                case_backup_dir.mkdir(parents=True, exist_ok=True)
                case_db = case_dir / "shim_internal.db"

                with sqlite3.connect(database.DB_PATH) as src, sqlite3.connect(case_db) as dest:
                    src.backup(dest)
                if (database.DB_PATH.parent / "secret.key").exists():
                    (case_dir / "secret.key").write_bytes((database.DB_PATH.parent / "secret.key").read_bytes())

                for f_idx, (ftype, age) in enumerate(file_specs):
                    target_file = case_backup_dir / f"shim_internal_{idx}_{f_idx}.bak"
                    src_proto = proto_compatible if ftype == "compat" else proto_incompatible
                    with sqlite3.connect(src_proto) as src, sqlite3.connect(target_file) as dest:
                        src.backup(dest)
                    mtime = fixed_now_ts - age
                    os.utime(target_file, (mtime, mtime))

                asyncio.run(run_scheduler_test(case_db, expect_create))

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
