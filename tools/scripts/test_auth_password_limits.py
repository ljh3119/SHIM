from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    original_data_dir = os.environ.get("SHIM_DATA_DIR")
    original_secret = os.environ.get("SHIM_SECRET_KEY")

    with tempfile.TemporaryDirectory(prefix="shim_password_test_") as temp_dir:
        os.environ["SHIM_DATA_DIR"] = temp_dir
        os.environ.pop("SHIM_SECRET_KEY", None)

        from src.app import auth, database, utils

        try:
            ascii_71 = "Aa1!" + ("x" * 67)
            ascii_72 = ascii_71 + "x"
            ascii_73 = ascii_72 + "x"
            assert [len(value.encode("utf-8")) for value in (ascii_71, ascii_72, ascii_73)] == [71, 72, 73]

            for password in (ascii_71, ascii_72):
                hashed = auth.get_password_hash(password)
                assert auth.verify_password(password, hashed)
                assert utils.validate_password_strength(password) is None

            boundary_hash = auth.get_password_hash(ascii_72)
            assert auth.verify_password(ascii_73, boundary_hash) is False
            assert "72바이트" in utils.validate_password_strength(ascii_73)
            try:
                auth.get_password_hash(ascii_73)
            except ValueError as exc:
                assert "72바이트" in str(exc)
            else:
                raise AssertionError("73바이트 비밀번호 해시는 거부해야 합니다.")

            korean_72 = ("가" * 22) + "Aa1!xx"
            emoji_72 = ("😀" * 16) + "Aa1!xxxx"
            for password in (korean_72, emoji_72):
                assert len(password.encode("utf-8")) == 72
                hashed = auth.get_password_hash(password)
                assert auth.verify_password(password, hashed)
                assert utils.validate_password_strength(password) is None
                assert "72바이트" in utils.validate_password_strength(password + "x")

            original_checkpw = auth.bcrypt.checkpw
            auth.bcrypt.checkpw = lambda *_: (_ for _ in ()).throw(ValueError("bcrypt boundary"))
            try:
                assert auth.verify_password("short", boundary_hash) is False
            finally:
                auth.bcrypt.checkpw = original_checkpw

            print("[PASS] AUTH-001 bcrypt byte-limit checks completed.")
            return 0
        finally:
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
