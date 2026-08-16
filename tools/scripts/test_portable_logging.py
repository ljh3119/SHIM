from __future__ import annotations

import logging
import atexit
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ORIGINAL_DATA_DIR = os.environ.get("SHIM_DATA_DIR")
_TEST_DATA_DIR = tempfile.mkdtemp(prefix="shim_portable_logging_")
os.environ["SHIM_DATA_DIR"] = _TEST_DATA_DIR


def _cleanup_test_data() -> None:
    if _ORIGINAL_DATA_DIR is None:
        os.environ.pop("SHIM_DATA_DIR", None)
    else:
        os.environ["SHIM_DATA_DIR"] = _ORIGINAL_DATA_DIR
    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)


atexit.register(_cleanup_test_data)

from portable import shim_portable


class _ExitedProcess:
    def poll(self):
        return 7


class _FailedWorker:
    def __init__(self):
        self.wait_calls = []

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        return 7

    def kill(self):
        raise AssertionError("종료된 worker를 강제 종료하면 안 됩니다.")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(0.25)
    raise AssertionError(f"포터블 서버 health 확인 시간 초과: {last_error}")


def _test_windows_tray_shutdown() -> None:
    if os.name != "nt":
        return

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    assert not user32.FindWindowW("SHIMTrayClass", None), "기존 SHIM 트레이 인스턴스가 테스트를 방해합니다."

    worker_data_dir = Path(tempfile.mkdtemp(prefix="shim_portable_tray_shutdown_"))
    port = _free_port()
    env = os.environ.copy()
    env["SHIM_DATA_DIR"] = str(worker_data_dir)
    env["SHIM_ENABLE_OPENAPI"] = "false"
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(PROJECT_ROOT), env.get("PYTHONPATH"))))
    bootstrap = (
        "import sys; from portable import shim_portable as s; "
        "notify=s.shell32.Shell_NotifyIconW; "
        "s.shell32.Shell_NotifyIconW=lambda message,data: "
        "1 if message==s.NIM_ADD else notify(message,data); "
        f"sys.argv=['shim_portable.py','--server','--port','{port}']; s.main()"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", bootstrap],
        cwd=PROJECT_ROOT,
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    try:
        _wait_for_health(port)

        deadline = time.monotonic() + 10
        tray_window = None
        while time.monotonic() < deadline:
            tray_window = user32.FindWindowW("SHIMTrayClass", None)
            if tray_window:
                break
            time.sleep(0.1)
        assert tray_window, "SHIM 트레이 창을 찾지 못했습니다."
        assert user32.PostMessageW(tray_window, 273, 1002, 0), "트레이 종료 메시지 전송 실패"
        assert proc.wait(timeout=30) == 0

        master_log = (worker_data_dir / "log" / "shim-master.log").read_text(encoding="utf-8")
        app_log = (worker_data_dir / "log" / "shim-app.log").read_text(encoding="utf-8")
        assert "자식 프로세스가 응답하지 않아 강제 종료합니다" not in master_log
        assert "Graceful shutdown event received." in app_log
        assert "Application shutdown complete." in app_log
        assert "Lifespan shutdown: Database connection pool disposed successfully." in app_log

        db_path = worker_data_dir / "shim_internal.db"
        assert db_path.is_file()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if not Path(f"{db_path}-wal").exists() and not Path(f"{db_path}-shm").exists():
                break
            time.sleep(0.1)
        assert not Path(f"{db_path}-wal").exists()
        assert not Path(f"{db_path}-shm").exists()
    finally:
        if proc.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        shutil.rmtree(worker_data_dir, ignore_errors=True)


def _test_windows_tray_failure_paths() -> None:
    if os.name != "nt":
        return

    original_proc = shim_portable._uvicorn_proc
    original_handle = shim_portable._shutdown_event_handle
    original_hwnd = shim_portable._hwnd
    try:
        failed_worker = _FailedWorker()
        shim_portable._uvicorn_proc = failed_worker
        shim_portable._shutdown_event_handle = None
        with (
            patch.object(shim_portable.time, "sleep"),
            patch.object(shim_portable.shell32, "Shell_NotifyIconW", return_value=True),
            patch.object(shim_portable.user32, "PostQuitMessage"),
            patch.object(shim_portable.os, "_exit") as forced_exit,
        ):
            shim_portable.graceful_exit(1)
        assert failed_worker.wait_calls == [15.0]
        forced_exit.assert_not_called()

        startup_event = shim_portable.threading.Event()
        startup_errors = []
        with (
            patch.object(shim_portable.user32, "RegisterClassW", return_value=1),
            patch.object(shim_portable.user32, "CreateWindowExW", return_value=1),
            patch.object(shim_portable.user32, "LoadIconW", return_value=1),
            patch.object(shim_portable.shell32, "Shell_NotifyIconW", return_value=False),
            patch.object(shim_portable.kernel32, "GetLastError", return_value=5),
        ):
            shim_portable.run_tray_icon_thread(65530, startup_event, startup_errors)
        assert startup_event.is_set()
        assert startup_errors == ["Failed to add tray icon. WinError=5"]

        failure_data_dir = Path(tempfile.mkdtemp(prefix="shim_portable_tray_failure_"))
        try:
            failure_env = os.environ.copy()
            failure_env["SHIM_DATA_DIR"] = str(failure_data_dir)
            failure_env["PYTHONPATH"] = os.pathsep.join(
                filter(None, (str(PROJECT_ROOT), failure_env.get("PYTHONPATH")))
            )
            failure_bootstrap = (
                "import sys; from portable import shim_portable as s; "
                "s.shell32.Shell_NotifyIconW=lambda message,data: 0; "
                "sys.argv=['shim_portable.py','--server','--port','65530']; s.main()"
            )
            result = subprocess.run(
                [sys.executable, "-c", failure_bootstrap],
                cwd=PROJECT_ROOT,
                env=failure_env,
                timeout=10,
                check=False,
            )
            assert result.returncode != 0
            master_log = (failure_data_dir / "log" / "shim-master.log").read_text(encoding="utf-8")
            assert "Failed to add tray icon" in master_log
            assert "[TRAY INIT ERROR]" in master_log
            assert not (failure_data_dir / "shim_internal.db").exists()
        finally:
            shutil.rmtree(failure_data_dir, ignore_errors=True)
    finally:
        shim_portable._uvicorn_proc = original_proc
        shim_portable._shutdown_event_handle = original_handle
        shim_portable._hwnd = original_hwnd


def main() -> None:
    data_dir = Path(os.environ["SHIM_DATA_DIR"])
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)

    try:
        handler = shim_portable.configure_background_logging("shim-app.log", max_bytes=512)
        assert handler.maxBytes == 512
        assert handler.backupCount == 3
        assert handler.encoding.lower().replace("-", "") == "utf8"
        assert root_logger.handlers == [handler]
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            assert logging.getLogger(name).handlers == []
            assert logging.getLogger(name).propagate

        for index in range(100):
            print(f"portable rotation test {index:03d} " + ("x" * 80))
        print("포터블 한글 로그 검증")
        sys.stdout.flush()
        handler.flush()

        log_files = list((data_dir / "log").glob("shim-app.log*"))
        assert 2 <= len(log_files) <= 4, log_files
        assert (data_dir / "log" / "shim-app.log").is_file()
        assert any("포터블 한글 로그 검증" in path.read_text(encoding="utf-8") for path in log_files)

        corrupt_db = data_dir / "shim_internal.db"
        corrupt_db.write_bytes(b"not-a-sqlite-database")
        from src.app.services.ops import run_backup_and_rotate
        assert run_backup_and_rotate(corrupt_db) is None
        sys.stdout.flush()
        assert "[SHIM BACKUP ERROR]" in (data_dir / "log" / "shim-app.log").read_text(encoding="utf-8")

        with patch.object(handler, "doRollover", side_effect=PermissionError("rollover denied")) as rollover:
            logging.getLogger("shim.test").info("runtime log failure " + ("x" * 1024))
            assert rollover.call_count == 1

        started, exit_code = shim_portable.wait_for_background_start(
            _ExitedProcess(), 65530, attempts=1, delay=0
        )
        assert not started
        assert exit_code == 7

        with patch.object(Path, "mkdir", side_effect=PermissionError("log denied")):
            try:
                shim_portable.configure_background_logging("shim-master.log")
            except PermissionError:
                pass
            else:
                raise AssertionError("로그 디렉터리 초기화 실패를 숨기면 안 됩니다.")

        worker_data_dir = Path(tempfile.mkdtemp(prefix="shim_portable_worker_failure_"))
        try:
            (worker_data_dir / "shim_internal.db").write_bytes(b"not-a-sqlite-database")
            worker_env = os.environ.copy()
            worker_env["SHIM_DATA_DIR"] = str(worker_data_dir)
            worker_env["PYTHONPATH"] = os.pathsep.join(
                filter(None, (str(PROJECT_ROOT), worker_env.get("PYTHONPATH")))
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "portable" / "shim_portable.py"),
                    "--uvicorn-worker",
                    "--port",
                    "65530",
                ],
                cwd=PROJECT_ROOT,
                env=worker_env,
                timeout=20,
                check=False,
            )
            assert result.returncode != 0
            worker_log = worker_data_dir / "log" / "shim-app.log"
            assert "[DB INIT ERROR]" in worker_log.read_text(encoding="utf-8")
        finally:
            shutil.rmtree(worker_data_dir, ignore_errors=True)

        _test_windows_tray_failure_paths()
        _test_windows_tray_shutdown()
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            handler.close()
        for handler in original_handlers:
            root_logger.addHandler(handler)

    print("[PASS] OPS-004 portable logging, early-exit, and tray shutdown checks completed.")


if __name__ == "__main__":
    main()
