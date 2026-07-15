from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PUBLIC_FALLBACK_KEY = "shim_change_this_secret_key_before_operation"


def _restore_env(name: str, original: str | None) -> None:
    if original is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = original


def main() -> int:
    original_data_dir = os.environ.get("SHIM_DATA_DIR")
    original_secret = os.environ.get("SHIM_SECRET_KEY")

    with tempfile.TemporaryDirectory(prefix="shim_secret_key_test_") as temp_dir:
        os.environ["SHIM_DATA_DIR"] = temp_dir
        os.environ.pop("SHIM_SECRET_KEY", None)

        from src.app import auth, database

        try:
            secret_file = Path(temp_dir) / "secret.key"
            generated_key = auth._resolve_secret_key()

            assert generated_key != PUBLIC_FALLBACK_KEY
            assert secret_file.exists()
            assert auth._resolve_secret_key() == generated_key

            forged_token = auth.jwt.encode(
                {"sub": "admin", "token_version": 0},
                PUBLIC_FALLBACK_KEY,
                algorithm=auth.ALGORITHM,
            )
            forged_request = SimpleNamespace(cookies={"access_token": forged_token})
            assert auth.get_payload_from_token(forged_request) is None

            auth.clear_encryption_key_cache()
            assert auth.get_encryption_key() is None, (
                "자동 생성 JWT 키는 기존 설계대로 PII 암호화 키로 사용하면 안 됩니다."
            )

            os.environ["SHIM_SECRET_KEY"] = "explicit_test_secret"
            assert auth._resolve_secret_key() == "explicit_test_secret"
            auth.clear_encryption_key_cache()
            assert auth.get_encryption_key() is not None

            os.environ["SHIM_SECRET_KEY"] = PUBLIC_FALLBACK_KEY
            try:
                auth._resolve_secret_key()
            except RuntimeError:
                pass
            else:
                raise AssertionError("알려진 공개 기본 JWT 키는 기동 전에 거부해야 합니다.")

            os.environ.pop("SHIM_SECRET_KEY", None)
            auth.clear_encryption_key_cache()

            blocked_path = Path(temp_dir) / "not_a_directory"
            blocked_path.write_text("block directory creation", encoding="utf-8")
            original_resolver = auth._resolve_data_dir
            auth._resolve_data_dir = lambda: blocked_path
            try:
                try:
                    auth._resolve_secret_key()
                except RuntimeError:
                    pass
                else:
                    raise AssertionError(
                        "secret.key를 저장할 수 없을 때 공개 키로 계속 기동하지 말고 "
                        "RuntimeError로 실패해야 합니다."
                    )
            finally:
                auth._resolve_data_dir = original_resolver

            print("[PASS] SEC-001 secret key generation and fail-fast behavior verified.")
            return 0
        finally:
            auth.clear_encryption_key_cache()
            database.engine.dispose()
            _restore_env("SHIM_SECRET_KEY", original_secret)
            _restore_env("SHIM_DATA_DIR", original_data_dir)


if __name__ == "__main__":
    raise SystemExit(main())
