import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_APP_DATA = Path(tempfile.mkdtemp(prefix="shim_recovery_test_"))
os.environ["SHIM_DATA_DIR"] = str(TEST_APP_DATA)

from src.app.services import ops


def create_valid_db(path: Path, value: str) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO marker (value) VALUES (?)", (value,))
        connection.commit()
    finally:
        connection.close()


def main() -> None:
    case_dir = TEST_APP_DATA / "case"
    case_dir.mkdir()
    db_path = case_dir / "shim_internal.db"

    create_valid_db(db_path, "healthy")
    ops.verify_and_recover_db(db_path)
    assert ops._is_sqlite_healthy(db_path)

    db_path.write_bytes(b"not-a-sqlite-database")
    original_corrupt_bytes = db_path.read_bytes()
    try:
        ops.verify_and_recover_db(db_path)
    except RuntimeError as error:
        assert "no valid backup" in str(error)
    else:
        raise AssertionError("Corrupt DB without a valid backup must stop startup.")
    assert db_path.read_bytes() == original_corrupt_bytes

    backup_dir = case_dir / "backup"
    backup_dir.mkdir()
    valid_backup = backup_dir / "shim_internal_older.bak"
    create_valid_db(valid_backup, "restored")
    invalid_backup = backup_dir / "shim_internal_newer.bak"
    invalid_backup.write_bytes(b"broken-backup")
    os.utime(valid_backup, (1, 1))
    os.utime(invalid_backup, None)

    ops.verify_and_recover_db(db_path)
    connection = sqlite3.connect(db_path)
    try:
        restored_value = connection.execute("SELECT value FROM marker").fetchone()[0]
    finally:
        connection.close()
    assert restored_value == "restored"
    assert list(case_dir.glob("shim_internal.db_corrupted_*"))

    before_access_error = db_path.read_bytes()
    with patch.object(ops.sqlite3, "connect", side_effect=PermissionError("access denied")):
        try:
            ops.verify_and_recover_db(db_path)
        except RuntimeError as error:
            assert "could not complete" in str(error)
        else:
            raise AssertionError("Unexpected file access errors must stop startup.")
    assert db_path.read_bytes() == before_access_error

    print("[PASS] DB recovery preserves originals and restores only validated backups.")


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(TEST_APP_DATA, ignore_errors=True)
