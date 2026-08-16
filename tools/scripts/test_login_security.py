from __future__ import annotations

import base64
import atexit
import json
import os
import shutil
import tempfile
from unittest.mock import patch

TEST_DATA_DIR = tempfile.mkdtemp(prefix="shim_login_security_")
os.environ["SHIM_DATA_DIR"] = TEST_DATA_DIR
atexit.register(shutil.rmtree, TEST_DATA_DIR, True)

from fastapi.testclient import TestClient
from starlette.requests import Request

from src.app import auth, database, models
from src.app.main import app


GENERIC_ERROR = "아이디 또는 비밀번호가 잘못되었습니다."
INACTIVE_ERROR = "비활성화된 계정입니다."


def _request_with_token(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"cookie", f"access_token=Bearer {token}".encode("ascii"))],
        }
    )


def _base64url_json(value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def main() -> None:
    assert auth.DUMMY_PASSWORD_HASH.startswith("$2b$12$")

    password_72 = "가" * 24
    password_73 = password_72 + "x"
    ascii_72 = "a" * 72
    ascii_73 = ascii_72 + "a"
    assert len(password_72.encode("utf-8")) == 72
    assert len(password_73.encode("utf-8")) == 73
    assert len(ascii_72.encode("utf-8")) == 72
    assert len(ascii_73.encode("utf-8")) == 73

    stored_hash = auth.get_password_hash(password_72)
    with patch.object(auth.bcrypt, "checkpw", wraps=auth.bcrypt.checkpw) as checkpw:
        assert auth.verify_login_password(password_72, stored_hash)
        assert checkpw.call_count == 1

    with patch.object(auth.bcrypt, "checkpw", wraps=auth.bcrypt.checkpw) as checkpw:
        assert not auth.verify_login_password(password_72, None)
        assert checkpw.call_count == 1

    with patch.object(auth.bcrypt, "checkpw", wraps=auth.bcrypt.checkpw) as checkpw:
        assert not auth.verify_login_password(password_73, stored_hash)
        assert not auth.verify_login_password(password_73, None)
        assert checkpw.call_count == 0

    with patch.object(auth.bcrypt, "checkpw", wraps=auth.bcrypt.checkpw) as checkpw:
        assert not auth.verify_login_password("valid-length", "malformed-hash")
        assert checkpw.call_count == 1

    with patch.object(auth.bcrypt, "checkpw", return_value=True) as checkpw:
        assert not auth.verify_login_password("valid-length", "")
        assert checkpw.call_count == 1

    ascii_hash = auth.get_password_hash(ascii_72)
    assert auth.verify_login_password(ascii_72, ascii_hash)
    assert not auth.verify_login_password(ascii_73, ascii_hash)

    with TestClient(app) as client:
        with patch.object(auth.bcrypt, "checkpw", wraps=auth.bcrypt.checkpw) as checkpw:
            response = client.post(
                "/login",
                data={"user_id": "missing-security-test", "password": password_72},
            )
            assert response.status_code == 200
            assert GENERIC_ERROR in response.text
            assert INACTIVE_ERROR not in response.text
            assert checkpw.call_count == 1

        db = database.SessionLocal()
        try:
            db.add(
                models.Users(
                    user_id="inactive-security-test",
                    user_name="비활성 테스트",
                    password=auth.get_password_hash("Correct1!"),
                    is_active=False,
                    role="STAFF",
                )
            )
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/login",
            data={"user_id": "inactive-security-test", "password": "Wrong1!!"},
        )
        assert GENERIC_ERROR in response.text
        assert INACTIVE_ERROR not in response.text

        response = client.post(
            "/login",
            data={"user_id": "inactive-security-test", "password": "Correct1!"},
        )
        assert INACTIVE_ERROR in response.text

    hs256_token = auth.create_access_token({"sub": "algorithm-test"})
    assert auth.get_payload_from_token(_request_with_token(hs256_token))["sub"] == "algorithm-test"

    es256_token = ".".join(
        (
            _base64url_json({"alg": "ES256", "typ": "JWT"}),
            _base64url_json({"sub": "algorithm-test"}),
            "invalid-signature",
        )
    )
    assert auth.get_payload_from_token(_request_with_token(es256_token)) is None

    database.engine.dispose()
    print("[PASS] AUTH-003 login timing, byte boundary, account state, and JWT algorithm checks completed.")


if __name__ == "__main__":
    main()
