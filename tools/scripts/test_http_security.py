import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}


def assert_security_headers(response, *, external_docs: bool = False) -> None:
    for name, value in EXPECTED_HEADERS.items():
        assert response.headers.get(name) == value, (name, response.headers)
    csp = response.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "https://" in csp if external_docs else "https://" not in csp
    assert "strict-transport-security" not in response.headers


def check_openapi_enabled() -> None:
    from fastapi.testclient import TestClient
    from src.app.main import app

    assert app.docs_url == "/docs"
    assert app.redoc_url == "/redoc"
    assert app.openapi_url == "/openapi.json"
    with TestClient(app) as client:
        for path in ("/docs", "/redoc"):
            response = client.get(path)
            assert response.status_code == 200, (path, response.text)
            assert_security_headers(response, external_docs=True)
        schema = client.get("/openapi.json")
        assert schema.status_code == 200
        assert_security_headers(schema)


def main() -> None:
    if sys.argv[1:] == ["--openapi-enabled"]:
        check_openapi_enabled()
        return

    os.environ.pop("SHIM_ENABLE_OPENAPI", None)

    from fastapi.testclient import TestClient
    from fastapi.responses import JSONResponse
    from src.app import main as app_main
    from src.app.dependencies import NotAuthenticatedException, PermissionDeniedException

    @app_main.app.get("/api/_test/unauthorized", include_in_schema=False)
    def unauthorized():
        raise NotAuthenticatedException()

    @app_main.app.get("/api/_test/forbidden", include_in_schema=False)
    def forbidden():
        raise PermissionDeniedException()

    @app_main.app.get("/_test/handled-500", include_in_schema=False)
    def handled_error():
        return JSONResponse(status_code=500, content={"detail": "handled"})

    assert app_main.app.docs_url is None
    assert app_main.app.redoc_url is None
    assert app_main.app.openapi_url is None

    original_db_path = app_main.DB_PATH
    with TestClient(app_main.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}
        assert_security_headers(health)

        with patch.object(app_main, "_load_branding_into_request", side_effect=RuntimeError("branding failed")):
            assert client.get("/health").status_code == 200

        for path, expected in (
            ("/", 200),
            ("/static/js/time.js", 200),
            ("/logout", 302),
            ("/missing", 404),
            ("/api/_test/unauthorized", 401),
            ("/api/_test/forbidden", 403),
            ("/_test/handled-500", 500),
        ):
            response = client.get(path, follow_redirects=False)
            assert response.status_code == expected, (path, response.status_code, response.text)
            assert_security_headers(response)

        for path in ("/docs", "/redoc", "/openapi.json"):
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 404, (path, response.status_code)
            assert_security_headers(response)

        missing_db = original_db_path.parent / "missing-health.db"
        app_main.DB_PATH = missing_db
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}
        assert not missing_db.exists()

        empty_db = original_db_path.parent / "empty-health.db"
        empty_db.write_bytes(b"")
        app_main.DB_PATH = empty_db
        assert client.get("/health").status_code == 503

        partial_db = original_db_path.parent / "partial-health.db"
        with sqlite3.connect(partial_db) as connection:
            connection.execute("CREATE TABLE system_settings (id INTEGER PRIMARY KEY)")
        app_main.DB_PATH = partial_db
        assert client.get("/health").status_code == 503

        app_main.DB_PATH = original_db_path
        private_error = "G:/private/shim_internal.db is locked"
        with patch.object(app_main.sqlite3, "connect", side_effect=sqlite3.OperationalError(private_error)):
            response = client.get("/health")
        assert response.status_code == 503
        assert private_error not in response.text

    app_main.DB_PATH = original_db_path

    with tempfile.TemporaryDirectory(prefix="shim_openapi_enabled_") as data_dir:
        env = os.environ.copy()
        env["SHIM_DATA_DIR"] = data_dir
        env["SHIM_ENABLE_OPENAPI"] = "TrUe"
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--openapi-enabled"],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    print("[PASS] OPS-003/SEC-002/SEC-003 health, OpenAPI, and security header checks completed.")


if __name__ == "__main__":
    main()
