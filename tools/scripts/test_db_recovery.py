from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_APP_DATA = Path(tempfile.mkdtemp(prefix="shim_recovery_test_"))
os.environ["SHIM_DATA_DIR"] = str(TEST_APP_DATA)

from src.app import models
from src.app.migrations import MIGRATIONS, run_all_migrations
from src.app.services import ops


FINGERPRINT = "PLAINTEXT_MODE"


def create_compatible_db(path: Path, marker: str = "compatible") -> None:
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    models.Base.metadata.create_all(engine)
    run_all_migrations(engine)
    session = sessionmaker(bind=engine)()
    try:
        session.add(models.SystemSettings(key_hash_snapshot=FINGERPRINT))
        session.commit()
    finally:
        session.close()
        engine.dispose()
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE recovery_marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO recovery_marker (value) VALUES (?)", (marker,))


def copy_case(source: Path, target: Path, sql: str, parameters=()) -> Path:
    shutil.copy2(source, target)
    with sqlite3.connect(target) as connection:
        connection.execute(sql, parameters)
    return target


def assert_incompatible(path: Path, expected: str) -> None:
    compatible, reason = ops._validate_recovery_candidate(path, FINGERPRINT)
    assert not compatible
    assert expected in reason, reason


def expect_runtime_error(callback, expected: str) -> None:
    try:
        callback()
    except RuntimeError as error:
        assert expected in str(error), str(error)
    else:
        raise AssertionError(f"RuntimeError expected: {expected}")


def main() -> None:
    case_dir = TEST_APP_DATA / "case"
    case_dir.mkdir()
    baseline = case_dir / "baseline.db"
    create_compatible_db(baseline)
    assert ops._validate_recovery_candidate(baseline, FINGERPRINT) == (True, "ok")

    current_migrations = {version for version, _ in MIGRATIONS}
    missing_migration = case_dir / "missing-migration.db"
    missing_id = sorted(current_migrations)[0]
    copy_case(baseline, missing_migration, "DELETE FROM schema_versions WHERE version = ?", (missing_id,))
    assert_incompatible(missing_migration, "missing=")

    unknown_migration = case_dir / "unknown-migration.db"
    copy_case(baseline, unknown_migration, "INSERT INTO schema_versions(version) VALUES ('future_v999')")
    assert_incompatible(unknown_migration, "unknown=")

    missing_table = case_dir / "missing-table.db"
    copy_case(baseline, missing_table, "DROP TABLE notifications")
    assert_incompatible(missing_table, "missing tables")

    for file_name, sql, expected in (
        ("missing-user-column.db", "ALTER TABLE users DROP COLUMN token_version", "missing columns in users"),
        ("missing-settings-column.db", "ALTER TABLE system_settings DROP COLUMN key_hash_snapshot", "missing columns in system_settings"),
        ("missing-leave-column.db", "ALTER TABLE leaves DROP COLUMN snapshot_slot_label", "missing columns in leaves"),
        ("no-settings.db", "DELETE FROM system_settings", "row count is 0"),
        ("null-fingerprint.db", "UPDATE system_settings SET key_hash_snapshot = NULL", "is empty"),
        ("blank-fingerprint.db", "UPDATE system_settings SET key_hash_snapshot = '   '", "is empty"),
        ("wrong-fingerprint.db", "UPDATE system_settings SET key_hash_snapshot = 'wrong'", "fingerprint mismatch"),
    ):
        target = case_dir / file_name
        copy_case(baseline, target, sql)
        assert_incompatible(target, expected)

    two_settings = case_dir / "two-settings.db"
    shutil.copy2(baseline, two_settings)
    engine = create_engine(f"sqlite:///{two_settings.as_posix()}")
    session = sessionmaker(bind=engine)()
    try:
        session.add(models.SystemSettings(key_hash_snapshot=FINGERPRINT))
        session.commit()
    finally:
        session.close()
        engine.dispose()
    assert_incompatible(two_settings, "row count is 2")

    db_path = case_dir / "shim_internal.db"
    create_compatible_db(db_path, "healthy")
    ops.verify_and_recover_db(db_path, FINGERPRINT)

    db_path.write_bytes(b"not-a-sqlite-database")
    original_corrupt_bytes = db_path.read_bytes()
    expect_runtime_error(lambda: ops.verify_and_recover_db(db_path, FINGERPRINT), "no compatible backup")
    assert db_path.read_bytes() == original_corrupt_bytes

    backup_dir = case_dir / "backup"
    backup_dir.mkdir()
    compatible_backup = backup_dir / "shim_internal_older.bak"
    create_compatible_db(compatible_backup, "restored")
    incompatible_backup = backup_dir / "shim_internal_newer.bak"
    copy_case(
        compatible_backup,
        incompatible_backup,
        "UPDATE system_settings SET key_hash_snapshot = 'other-key'",
    )
    os.utime(compatible_backup, (1, 1))
    os.utime(incompatible_backup, None)

    Path(f"{db_path}-wal").write_bytes(b"wal-preserved")
    Path(f"{db_path}-shm").write_bytes(b"shm-preserved")
    original_connect = ops.sqlite3.connect

    def run_with_forced_corruption():
        first_check = True

        def connect(database, *args, **kwargs):
            nonlocal first_check
            if first_check and str(database) == str(db_path):
                first_check = False
                raise sqlite3.DatabaseError("forced corruption")
            return original_connect(database, *args, **kwargs)

        with patch.object(ops.sqlite3, "connect", side_effect=connect):
            return ops.verify_and_recover_db(db_path, FINGERPRINT)

    run_with_forced_corruption()
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT value FROM recovery_marker").fetchone()[0] == "restored"
    connection.close()
    assert list(case_dir.glob("shim_internal.db_corrupted_*"))
    assert list(case_dir.glob("shim_internal.db-wal_corrupted_*"))
    assert list(case_dir.glob("shim_internal.db-shm_corrupted_*"))

    def reset_corrupt_with_sidecars():
        db_path.write_bytes(b"corrupt-again")
        Path(f"{db_path}-wal").write_bytes(b"wal-original")
        Path(f"{db_path}-shm").write_bytes(b"shm-original")

    reset_corrupt_with_sidecars()
    original_replace = ops.os.replace

    def fail_install(source, target):
        if Path(target) == db_path and ".restore_" in Path(source).name:
            raise PermissionError("install denied")
        return original_replace(source, target)

    with patch.object(ops.os, "replace", side_effect=fail_install):
        expect_runtime_error(
            run_with_forced_corruption,
            "Failed to install validated backup",
        )
    assert db_path.read_bytes() == b"corrupt-again"
    assert Path(f"{db_path}-wal").read_bytes() == b"wal-original"
    assert Path(f"{db_path}-shm").read_bytes() == b"shm-original"
    assert list(case_dir.glob(".shim_internal.db.restore_*.tmp"))

    reset_corrupt_with_sidecars()
    original_validator = ops._validate_recovery_candidate
    validation_count = 0

    def fail_final_validation(path, fingerprint):
        nonlocal validation_count
        validation_count += 1
        if Path(path) == db_path and validation_count >= 3:
            return False, "forced final failure"
        return original_validator(path, fingerprint)

    with patch.object(ops, "_validate_recovery_candidate", side_effect=fail_final_validation):
        expect_runtime_error(
            run_with_forced_corruption,
            "Installed database validation failed",
        )
    assert db_path.read_bytes() == b"corrupt-again"
    assert list(case_dir.glob("shim_internal.db_failed_restore_*"))

    reset_corrupt_with_sidecars()

    def fail_wal_isolation(source, target):
        if Path(source) == Path(f"{db_path}-wal"):
            raise PermissionError("wal isolation denied")
        return original_replace(source, target)

    with patch.object(ops.os, "replace", side_effect=fail_wal_isolation):
        expect_runtime_error(
            run_with_forced_corruption,
            "Failed to isolate database files",
        )
    assert db_path.read_bytes() == b"corrupt-again"
    assert Path(f"{db_path}-wal").exists()
    assert Path(f"{db_path}-shm").exists()

    reset_corrupt_with_sidecars()

    def fail_isolation_and_rollback(source, target):
        source_path = Path(source)
        target_path = Path(target)
        if source_path == Path(f"{db_path}-wal"):
            raise PermissionError("wal isolation denied")
        if target_path == db_path and "_corrupted_" in source_path.name:
            raise PermissionError("rollback denied")
        return original_replace(source, target)

    with patch.object(ops.os, "replace", side_effect=fail_isolation_and_rollback):
        expect_runtime_error(
            run_with_forced_corruption,
            "Database rollback failed",
        )
    assert not db_path.exists()
    assert list(case_dir.glob("shim_internal.db_corrupted_*"))
    assert Path(f"{db_path}-wal").exists()
    assert list(case_dir.glob(".shim_internal.db.restore_*.tmp"))

    print("[PASS] SEC-005 compatible backup validation and transactional recovery checks completed.")


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(TEST_APP_DATA, ignore_errors=True)
