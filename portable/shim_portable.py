import os
import sys
from pathlib import Path
import socket
import subprocess
import time
import argparse
import threading
import webbrowser
import logging
from logging.handlers import RotatingFileHandler

import uvicorn

# --- Native Windows System Tray Support via ctypes (Conditional Load for Cross-Platform Safety) ---
IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import msvcrt
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32

    # Win32 Function Prototypes (Declaring argtypes/restype to prevent 64-bit integer overflow issues)
    LRESULT = ctypes.c_ssize_t

    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

    # Mutex & Window Lookup APIs
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenEventW.restype = wintypes.HANDLE
    kernel32.SetEvent.argtypes = [wintypes.HANDLE]
    kernel32.SetEvent.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetLastError.argtypes = []
    kernel32.GetLastError.restype = wintypes.DWORD
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND

    user32.RegisterClassW.argtypes = [ctypes.c_void_p]
    user32.RegisterClassW.restype = wintypes.ATOM

    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID
    ]
    user32.CreateWindowExW.restype = wintypes.HWND

    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
    user32.LoadIconW.restype = wintypes.HICON

    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.c_void_p]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL

    user32.GetMessageW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = wintypes.BOOL

    user32.TranslateMessage.argtypes = [ctypes.c_void_p]
    user32.TranslateMessage.restype = wintypes.BOOL

    user32.DispatchMessageW.argtypes = [ctypes.c_void_p]
    user32.DispatchMessageW.restype = LRESULT

    user32.GetCursorPos.argtypes = [ctypes.c_void_p]
    user32.GetCursorPos.restype = wintypes.BOOL

    user32.CreatePopupMenu.argtypes = []
    user32.CreatePopupMenu.restype = wintypes.HMENU

    user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_void_p, ctypes.c_wchar_p]
    user32.AppendMenuW.restype = wintypes.BOOL

    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL

    user32.TrackPopupMenu.argtypes = [
        wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, wintypes.HWND, ctypes.c_void_p
    ]
    user32.TrackPopupMenu.restype = ctypes.c_int

    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL

    user32.DestroyMenu.argtypes = [wintypes.HMENU]
    user32.DestroyMenu.restype = wintypes.BOOL

    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.PostQuitMessage.restype = None

    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = LRESULT

    WM_USER = 1024
    WM_TRAYICON = WM_USER + 1
    WM_TRIGGER_BALLOON = WM_USER + 2
    WM_DESTROY = 2
    WM_COMMAND = 273
    WM_LBUTTONDBLCLK = 515
    WM_RBUTTONUP = 517

    ID_TRAY_OPEN = 1001
    ID_TRAY_EXIT = 1002
    ID_TRAY_TRIGGER_BALLOON = 1003

    NIM_ADD = 0
    NIM_MODIFY = 1
    NIM_DELETE = 2
    NIF_MESSAGE = 1
    NIF_ICON = 2
    NIF_TIP = 4
    NIF_INFO = 16
    SYNCHRONIZE = 0x00100000
    INFINITE = 0xFFFFFFFF
    WAIT_OBJECT_0 = 0

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", wintypes.HICON),
            ("szTip", wintypes.WCHAR * 128),
            ("dwState", wintypes.DWORD),
            ("dwStateMask", wintypes.DWORD),
            ("szInfo", wintypes.WCHAR * 256),
            ("uTimeout", wintypes.UINT),
            ("szInfoTitle", wintypes.WCHAR * 64),
            ("dwInfoFlags", wintypes.DWORD),
            ("guidItem", ctypes.c_byte * 16),
            ("hBalloonIcon", wintypes.HICON),
        ]

    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HICON),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    _nid = NOTIFYICONDATAW()
    _wndproc_delegate = WNDPROC(lambda h, m, w, l: user32.DefWindowProcW(h, m, w, l)) # Placeholder will be updated or overridden
else:
    msvcrt = None
    ctypes = None
    wintypes = None
    user32 = None
    shell32 = None
    kernel32 = None
    WM_USER = 1024
    WM_TRAYICON = 0
    WM_TRIGGER_BALLOON = 0
    WM_DESTROY = 0
    WM_COMMAND = 0
    WM_LBUTTONDBLCLK = 0
    WM_RBUTTONUP = 0
    ID_TRAY_OPEN = 0
    ID_TRAY_EXIT = 0
    ID_TRAY_TRIGGER_BALLOON = 0
    NIM_ADD = 0
    NIM_MODIFY = 0
    NIM_DELETE = 0
    NIF_MESSAGE = 0
    NIF_ICON = 0
    NIF_TIP = 0
    NIF_INFO = 0
    SYNCHRONIZE = 0
    INFINITE = 0
    WAIT_OBJECT_0 = 0

    class DummyStructure:
        pass

    NOTIFYICONDATAW = DummyStructure
    WNDCLASSW = DummyStructure
    WNDPROC = lambda x: x

    _nid = None
    _wndproc_delegate = None

_hwnd = None
_uvicorn_proc = None
_shim_mutex = None
_shutdown_event_handle = None

LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUP_COUNT = 3


class _PortableRotatingFileHandler(RotatingFileHandler):
    def handleError(self, record):
        # stderr도 이 handler로 연결되므로 표준 handleError의 stderr 출력은 재귀합니다.
        # 시작 시 파일을 열지 못한 경우는 생성자에서 예외가 발생해 별도로 기동을 중단합니다.
        return


class _LoggerWriter:
    """print/stdout 출력을 같은 프로세스의 단일 로그 handler로 전달합니다."""

    def __init__(self, logger, level):
        self.logger = logger
        self.level = level
        self._buffer = ""

    def write(self, message):
        self._buffer += str(message)
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.rstrip("\r"):
                self.logger.log(self.level, line.rstrip("\r"))
        return len(message)

    def flush(self):
        if self._buffer:
            self.logger.log(self.level, self._buffer.rstrip("\r"))
            self._buffer = ""

    def isatty(self):
        return False


def configure_background_logging(file_name: str, *, max_bytes: int = LOG_MAX_BYTES):
    from src.app.database import _resolve_data_dir

    log_dir = _resolve_data_dir() / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / file_name
    handler = _PortableRotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    root_logger = logging.getLogger()
    for existing in list(root_logger.handlers):
        root_logger.removeHandler(existing)
        existing.close()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(logging.INFO)

    sys.stdout = _LoggerWriter(logging.getLogger("shim.stdout"), logging.INFO)
    sys.stderr = _LoggerWriter(logging.getLogger("shim.stderr"), logging.ERROR)
    logging.getLogger("shim.portable").info("Background logging initialized: %s", file_name)
    return handler


def _close_shutdown_event():
    global _shutdown_event_handle
    if _shutdown_event_handle and IS_WINDOWS:
        kernel32.CloseHandle(_shutdown_event_handle)
    _shutdown_event_handle = None


def _wait_for_shutdown_event(event_handle, server):
    if kernel32.WaitForSingleObject(event_handle, INFINITE) == WAIT_OBJECT_0:
        logging.getLogger("shim.portable").info("Graceful shutdown event received.")
        server.should_exit = True


def release_mutex():
    global _shim_mutex
    if _shim_mutex and IS_WINDOWS:
        try:
            kernel32.CloseHandle(_shim_mutex)
        except Exception:
            pass
        _shim_mutex = None

def open_browser_url():
    global _current_port
    webbrowser.open(f"http://localhost:{_current_port}")

def cleanup_tray_icon(hwnd):
    if not hwnd:
        return
    nid = NOTIFYICONDATAW()
    nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    nid.hWnd = hwnd
    nid.uID = 1
    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))

def graceful_exit(hwnd):
    # 1. 종료 알림 팝업 전송 (NIM_MODIFY)
    nid = NOTIFYICONDATAW()
    nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    nid.hWnd = hwnd
    nid.uID = 1
    nid.uFlags = NIF_INFO
    nid.szInfoTitle = "SHIM 종료"
    nid.szInfo = "SHIM 서버가 안전하게 종료되었습니다."
    nid.dwInfoFlags = 1 # NIIF_INFO
    shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
    
    # 2. 콘솔 안내 및 지연
    print("\n[알림] 시스템을 안전하게 종료합니다...")
    time.sleep(1.5)
    
    # 3. 콘솔이 없는 Uvicorn worker에 named event로 정상 종료 요청
    global _uvicorn_proc
    shutdown_requested = False
    if _shutdown_event_handle:
        shutdown_requested = bool(kernel32.SetEvent(_shutdown_event_handle))
    if not shutdown_requested:
        print("[오류] 자식 프로세스 정상 종료 이벤트 전송 실패")
    if _uvicorn_proc:
        try:
            try:
                _uvicorn_proc.wait(timeout=15.0)
            except subprocess.TimeoutExpired:
                print("[알림] 자식 프로세스가 응답하지 않아 강제 종료합니다...")
                _uvicorn_proc.kill()
                _uvicorn_proc.wait(timeout=1.0)
        except Exception as e:
            print(f"[오류] 자식 프로세스 종료 시그널 전송 실패: {e}")
    
    # 4. 메시지 루프만 종료합니다. worker 종료 코드와 자원 정리는 master가 담당합니다.
    user32.PostQuitMessage(0)

def trigger_duplicate_warning_balloon(hwnd):
    nid = NOTIFYICONDATAW()
    nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    nid.hWnd = hwnd
    nid.uID = 1
    nid.uFlags = NIF_INFO
    nid.szInfoTitle = "SHIM 실행 중"
    nid.szInfo = "SHIM 연차 관리 시스템이 이미 이 경로에서 백그라운드로 실행 중입니다."
    nid.dwInfoFlags = 1 # NIIF_INFO
    shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

def wnd_proc(hwnd, msg, wparam, lparam):
    if msg == WM_TRAYICON:
        if lparam == WM_RBUTTONUP:
            pos = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pos))
            menu = user32.CreatePopupMenu()
            user32.AppendMenuW(menu, 0, ctypes.c_void_p(ID_TRAY_OPEN), "SHIM 브라우저 열기")
            user32.AppendMenuW(menu, 0, ctypes.c_void_p(ID_TRAY_EXIT), "종료")
            user32.SetForegroundWindow(hwnd)
            cmd = user32.TrackPopupMenu(menu, 0x0002 | 0x0100, pos.x, pos.y, 0, hwnd, None)
            user32.PostMessageW(hwnd, 0, 0, 0) # Workaround for TrackPopupMenu outside click bug
            user32.DestroyMenu(menu)
            
            if cmd == ID_TRAY_OPEN:
                open_browser_url()
            elif cmd == ID_TRAY_EXIT:
                graceful_exit(hwnd)
        elif lparam == WM_LBUTTONDBLCLK:
            open_browser_url()
    elif msg == WM_COMMAND:
        cmd_id = wparam & 0xFFFF
        if cmd_id == ID_TRAY_OPEN:
            open_browser_url()
        elif cmd_id == ID_TRAY_EXIT:
            graceful_exit(hwnd)
        elif cmd_id == ID_TRAY_TRIGGER_BALLOON:
            trigger_duplicate_warning_balloon(hwnd)
    elif msg == WM_TRIGGER_BALLOON:
        trigger_duplicate_warning_balloon(hwnd)
    elif msg == WM_DESTROY:
        user32.PostQuitMessage(0)
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


_wndproc_delegate = WNDPROC(wnd_proc)

def run_tray_icon_thread(port, startup_event, startup_errors):
    global _current_port, _nid, _hwnd, _wndproc_delegate
    _current_port = port
    logger = logging.getLogger("shim.portable")

    def fail_startup(message):
        logger.error(message)
        startup_errors.append(message)
        startup_event.set()

    wc = WNDCLASSW()
    wc.lpfnWndProc = _wndproc_delegate
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = "SHIMTrayClass"
    atom = user32.RegisterClassW(ctypes.byref(wc))
    if not atom:
        error_code = kernel32.GetLastError()
        if error_code != 1410:  # ERROR_CLASS_ALREADY_EXISTS
            fail_startup(f"Failed to register tray window class. WinError={error_code}")
            return
    
    hwnd = user32.CreateWindowExW(
        0, wc.lpszClassName, "SHIM Tray Window",
        0, 0, 0, 0, 0, None, None, wc.hInstance, None
    )
    if not hwnd:
        fail_startup(f"Failed to create tray window. WinError={kernel32.GetLastError()}")
        return
    _hwnd = hwnd
    
    _nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    _nid.hWnd = hwnd
    _nid.uID = 1
    _nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_INFO
    _nid.uCallbackMessage = WM_TRAYICON
    
    # Try to load app icon from the executable (IDI_APPLICATION = 32512), fallback to IDI_ASTERISK (32516)
    # PyInstaller assigns resource ID 1 to the custom icon, so we try loading 1 first.
    hIcon = user32.LoadIconW(wc.hInstance, ctypes.c_void_p(1))
    if not hIcon:
        hIcon = user32.LoadIconW(None, ctypes.c_void_p(32516))
    _nid.hIcon = hIcon
    
    _nid.szTip = f"SHIM 연차 관리 시스템 (포트: {port})"
    _nid.szInfoTitle = "SHIM 실행 완료"
    _nid.szInfo = f"http://localhost:{port} 로 접속하세요."
    _nid.dwInfoFlags = 1 # NIIF_INFO
    
    if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(_nid)):
        fail_startup(f"Failed to add tray icon. WinError={kernel32.GetLastError()}")
        return
    startup_event.set()
    
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))



def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return False
        except OSError:
            return True


def resolve_port(start_port=8000) -> int:
    port = start_port
    max_port = port + 100
    while port <= max_port:
        if not is_port_in_use(port):
            return port
        port += 1
    return start_port


def wait_for_background_start(proc, port: int, *, attempts: int = 20, delay: float = 0.5):
    for _ in range(attempts):
        time.sleep(delay)
        exit_code = proc.poll()
        if exit_code is not None:
            return False, exit_code
        if is_port_in_use(port):
            return True, None
    return False, None


def input_with_timeout(prompt: str, timeout=5.0, default="") -> str:
    sys.stdout.write(prompt)
    sys.stdout.flush()
    start_time = time.time()
    input_str = ""
    while time.time() - start_time < timeout:
        if msvcrt.kbhit():
            char = msvcrt.getwche()
            if char in ("\r", "\n"):
                sys.stdout.write("\n")
                sys.stdout.flush()
                return input_str
            elif char == "\b":  # backspace
                if len(input_str) > 0:
                    input_str = input_str[:-1]
                    sys.stdout.write(" \b")
                    sys.stdout.flush()
            else:
                input_str += char
        time.sleep(0.05)
    sys.stdout.write("\n")
    sys.stdout.flush()
    return default


def choice_with_timeout(prompt: str, timeout=5.0, default="Y") -> str:
    choices_str = " [Y,N]? "
    sys.stdout.write(prompt + choices_str)
    sys.stdout.flush()
    start_time = time.time()
    while time.time() - start_time < timeout:
        if msvcrt.kbhit():
            char = msvcrt.getwche().upper()
            if char in ("Y", "N"):
                sys.stdout.write("\n")
                sys.stdout.flush()
                return char
            elif char in ("\r", "\n"):
                sys.stdout.write("\n")
                sys.stdout.flush()
                return default
        time.sleep(0.05)
    sys.stdout.write("\n")
    sys.stdout.flush()
    return default

def reset_admin_password_cmd():
    try:
        # Resolve runtime base path
        if getattr(sys, "frozen", False):
            runtime_base = Path(sys.executable).resolve().parent / "_internal"
            if str(runtime_base) not in sys.path:
                sys.path.insert(0, str(runtime_base))
        else:
            project_root = Path(__file__).resolve().parents[1]
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))

        from src.app import models, auth
        from src.app.database import SessionLocal

        db = SessionLocal()
        admin = db.query(models.Users).filter(models.Users.user_id == "admin").first()
        if not admin:
            print("[오류] 'admin' 계정이 존재하지 않습니다.")
            sys.exit(1)

        # 비밀번호를 '0000'으로 초기화 및 세션 즉시 만료 처리
        new_hash = auth.get_password_hash("0000")
        admin.password = new_hash
        admin.token_version = (admin.token_version or 0) + 1
        
        # 감사 로그 기록 (누가 했는지 알 수 없으므로 시스템 초기화 목적을 밝혀 'admin' 계정 ID로 기록)
        db.add(models.AuditLogs(
            actor_id="admin",
            action="RESET_ADMIN_PASSWORD",
            target_info="Admin:admin",
            old_data="*****",
            new_data="***** (Emergency Reset)"
        ))
        
        db.commit()
        db.close()
        print("[성공] 'admin' 계정의 비밀번호가 '0000'으로 초기화되었습니다.")
        sys.exit(0)
    except Exception as e:
        print(f"[오류] 초기화 중 문제가 발생했습니다: {str(e)}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true", help="Start as background server")
    parser.add_argument("--port", type=int, help="Port to run the server on")
    parser.add_argument("--foreground", "-f", action="store_true", help="Run in foreground mode (do not fork)")
    parser.add_argument("--uvicorn-worker", action="store_true", help="Start actual Uvicorn worker process")
    parser.add_argument("--shutdown-event", help=argparse.SUPPRESS)
    parser.add_argument("--reset-admin", action="store_true", help="Reset admin password to 0000")
    args = parser.parse_args()

    if args.reset_admin:
        reset_admin_password_cmd()
        sys.exit(0)

    # --uvicorn-worker 인자가 없을 때만 전역 뮤텍스를 통한 경로 단위 단일 기동 체크 수행
    global _shim_mutex
    if "--uvicorn-worker" not in sys.argv and sys.platform == "win32":
        try:
            import hashlib
            # 현재 실행 중인 파일 경로의 디렉토리 절대경로 해시를 획득해 로컬 Mutex 생성
            target_path = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
            h = hashlib.md5(str(target_path).encode("utf-8")).hexdigest()[:12]
            mutex_name = f"Local\\SHIM_Portable_Mutex_{h}"
            
            _shim_mutex = kernel32.CreateMutexW(None, True, mutex_name)
            if kernel32.GetLastError() == 183: # ERROR_ALREADY_EXISTS
                 # 기존 구동 중인 트레이 창 윈도우 룩업
                 hwnd_existing = user32.FindWindowW("SHIMTrayClass", None)
                 if hwnd_existing:
                     # 기존 마스터 트레이 윈도우에 벌룬 알림 메시지 Post (ID_TRAY_TRIGGER_BALLOON = 1003)
                     user32.PostMessageW(hwnd_existing, 273, 1003, 0)
                 sys.exit(0)
        except Exception as e:
            # 폐쇄망 보안 환경 등에 따라 예기치 않게 뮤텍스 생성이 막히는 경우 무중단 가동 유지
            print(f"[알림] 뮤텍스 중복 체크 우회 (이유: {e})")

    # Ensure runtime base path is set for PyInstaller execution
    if getattr(sys, "frozen", False):
        runtime_base = Path(sys.executable).resolve().parent / "_internal"
        if str(runtime_base) not in sys.path:
            sys.path.insert(0, str(runtime_base))
        if not os.getenv("SHIM_RUNTIME_BASE"):
            os.environ["SHIM_RUNTIME_BASE"] = str(runtime_base)

    if args.uvicorn_worker:
        # Foreground/Background Uvicorn Worker Process
        port = args.port if args.port else 8000
        os.environ["SHIM_PORT"] = str(port)
        try:
            configure_background_logging("shim-app.log")
        except Exception as e:
            print(f"[LOG INIT ERROR] Failed to initialize app log: {e}")
            sys.exit(1)
        worker_shutdown_handle = None
        try:
            if args.shutdown_event:
                if not IS_WINDOWS:
                    raise RuntimeError("Portable shutdown events require Windows.")
                worker_shutdown_handle = kernel32.OpenEventW(SYNCHRONIZE, False, args.shutdown_event)
                if not worker_shutdown_handle:
                    raise ctypes.WinError()
        except Exception as e:
            print(f"[SHUTDOWN INIT ERROR] Failed to open worker shutdown event: {e}")
            sys.exit(1)

        try:
            from tools.scripts.db_init import init_db
            init_db()
        except Exception as e:
            print(f"[DB INIT ERROR] Failed to initialize database: {e}")
            sys.exit(1)

        try:
            from src.app.main import app as fastapi_app
            if worker_shutdown_handle:
                config = uvicorn.Config(
                    fastapi_app,
                    host="0.0.0.0",
                    port=port,
                    reload=False,
                    log_config=None,
                )
                server = uvicorn.Server(config)
                threading.Thread(
                    target=_wait_for_shutdown_event,
                    args=(worker_shutdown_handle, server),
                    daemon=True,
                ).start()
                server.run()
            else:
                uvicorn.run(fastapi_app, host="0.0.0.0", port=port, reload=False, log_config=None)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"[SERVER ERROR] Uvicorn worker failed: {e}")
            sys.exit(1)
        finally:
            if worker_shutdown_handle:
                kernel32.CloseHandle(worker_shutdown_handle)
        sys.exit(0)

    if args.server:
        # Background Server Instance (Master process managing tray icon and worker process)
        port = args.port if args.port else 8000
        os.environ["SHIM_PORT"] = str(port)
        try:
            configure_background_logging("shim-master.log")
        except Exception as e:
            print(f"[LOG INIT ERROR] Failed to initialize master log: {e}")
            sys.exit(1)

        # Create the shutdown event before exposing the tray Exit action.
        global _shutdown_event_handle
        shutdown_event_name = f"Local\\SHIM_Portable_Shutdown_{os.getpid()}_{port}"
        _shutdown_event_handle = kernel32.CreateEventW(None, False, False, shutdown_event_name)
        if not _shutdown_event_handle:
            print(f"[SHUTDOWN INIT ERROR] Failed to create worker shutdown event: {ctypes.WinError()}")
            sys.exit(1)

        # Start native system tray thread and fail before spawning the worker if it cannot initialize.
        tray_startup_event = threading.Event()
        tray_startup_errors = []
        t = threading.Thread(
            target=run_tray_icon_thread,
            args=(port, tray_startup_event, tray_startup_errors),
            daemon=True,
        )
        t.start()
        if not tray_startup_event.wait(timeout=5.0):
            print("[TRAY INIT ERROR] Timed out while initializing the tray icon.")
            _close_shutdown_event()
            sys.exit(1)
        if tray_startup_errors:
            print(f"[TRAY INIT ERROR] {tray_startup_errors[0]}")
            _close_shutdown_event()
            sys.exit(1)

        # Spawn uvicorn worker process
        exe_path = sys.executable
        if getattr(sys, "frozen", False):
            cmd = [
                exe_path,
                "--uvicorn-worker",
                "--port",
                str(port),
                "--shutdown-event",
                shutdown_event_name,
            ]
        else:
            script_path = str(Path(__file__).resolve())
            cmd = [
                sys.executable,
                script_path,
                "--uvicorn-worker",
                "--port",
                str(port),
                "--shutdown-event",
                shutdown_event_name,
            ]

        # CREATE_NEW_PROCESS_GROUP = 0x00000200, CREATE_NO_WINDOW = 0x08000000
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000
        
        global _uvicorn_proc
        worker_exit_code = 1
        try:
            _uvicorn_proc = subprocess.Popen(cmd, creationflags=flags)
            worker_exit_code = _uvicorn_proc.wait()
        except KeyboardInterrupt:
            # Console interruption uses the same graceful event as the tray action.
            if _uvicorn_proc:
                try:
                    kernel32.SetEvent(_shutdown_event_handle)
                    try:
                        worker_exit_code = _uvicorn_proc.wait(timeout=15.0)
                    except subprocess.TimeoutExpired:
                        _uvicorn_proc.kill()
                        worker_exit_code = _uvicorn_proc.wait(timeout=1.0)
                except Exception:
                    pass
            else:
                worker_exit_code = 0
        finally:
            _close_shutdown_event()
            if _hwnd:
                cleanup_tray_icon(_hwnd)
        sys.exit(worker_exit_code)

    if args.foreground:
        # Foreground Interactive Instance
        port = args.port if args.port else resolve_port(8000)
        os.environ["SHIM_PORT"] = str(port)
        try:
            from tools.scripts.db_init import init_db
            init_db()
        except Exception as e:
            print(f"[DB INIT ERROR] Failed to initialize database: {e}")
            sys.exit(1)
        print("=" * 60)
        print("  쉼(SHIM) 연차 관리 시스템이 포그라운드에서 기동되었습니다.")
        print("=" * 60)
        print(f"  접속 주소: http://localhost:{port}")
        print("  ※ 이 창을 닫으면 SHIM 서비스가 종료됩니다.")
        print("=" * 60)
        print()

        try:
            from src.app.main import app as fastapi_app
            uvicorn.run(fastapi_app, host="0.0.0.0", port=port, reload=False)
        except KeyboardInterrupt:
            pass
        sys.exit(0)

    # Launcher Instance (Double-clicked or run without arguments)
    try:
        from src.app.database import _resolve_data_dir
        data_dir = _resolve_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        secret_file = data_dir / "secret.key"
        if not secret_file.exists():
            print("=" * 70)
            print("  [초기 설정] SHIM 시스템 보안 비밀키 (secret.key) 설정")
            print("=" * 70)
            print("  이 설정은 사용자 로그인 세션(JWT) 서명 및 DB 내 개인정보 암호화에 사용됩니다.")
            print("  (다른 기기/소켓 연결 연동 시에도 동일한 키값으로 일치시켜 사용이 가능합니다.)")
            print("")
            print("  [선택 안내]")
            print("  1. 직접 키 입력 (보안 강화 모드):")
            print("     - 입력한 문자열을 바탕으로 개인정보(이름, 연차사유)가 암호화되어 저장됩니다.")
            print("     - [주의] 기존 평문(간편) 모드 DB를 사용 중인 상태에서 임의로 비밀키를 지정하면")
            print("             데이터 정합성 및 기능 마비 방지를 위해 시스템 기동이 차단됩니다.")
            print("     - [중요] 추후 백업/이전 시 DB 파일과 함께 이 'secret.key' 파일도 반드시")
            print("             새로운 서버의 동일한 위치로 복사해 주어야 정상 구동됩니다.")
            print("  2. 미입력 후 엔터 (간편 포터블 모드):")
            print("     - 보안 키가 임의로 자동 생성되며, 데이터베이스는 암호화 없이 저장됩니다.")
            print("     - 이 경우 'secret.key' 복사 없이 DB 파일 단독 이동만으로도 이관이 가능합니다.")
            print("-" * 70)
            user_key = input("  사용할 비밀키 입력 (생략 시 엔터): ").strip()
            if user_key:
                secret_file.write_text(user_key, encoding="utf-8")
                print("")
                print(f"  [완료] 입력하신 비밀키가 '{secret_file.name}'에 안전하게 저장되었습니다.")
                print("  ※ 추후 이관/복구 시 DB 파일과 이 secret.key 파일을 세트로 복사해 주세요.")
            else:
                import secrets
                new_key = secrets.token_urlsafe(48)
                secret_file.write_text(f"# AUTO-GENERATED JWT KEY - DO NOT USE FOR DB COLUMN ENCRYPTION\n{new_key}", encoding="utf-8")
                print("")
                print("  [완료] 무작위 비밀키가 자동으로 생성되었습니다. (개인정보 암호화 미적용)")
            print("=" * 70)
            print()
    except Exception as e:
        print(f"[경고] 초기 비밀키 설정 중 오류 발생: {e}")

    print()
    port_input = input("사용할 포트 번호를 입력하세요 [기본값: 8000]: ")
    try:
        start_port = int(port_input.strip()) if port_input.strip() else 8000
    except ValueError:
        print("[오류] 올바른 포트 번호가 아닙니다. 기본값 8000으로 진행합니다.")
        start_port = 8000

    port = start_port
    while True:
        if not is_port_in_use(port):
            break

        next_port = port + 1
        print(f"\n포트 {port} 번은 이미 다른 프로그램에서 사용 중입니다.")
        choice = choice_with_timeout(f"대체 포트 {next_port} 번으로 구동하시겠습니까?", timeout=5.0, default="Y")
        if choice == "N":
            print("[알림] 구동이 사용자에 의해 취소되었습니다.")
            time.sleep(2)
            sys.exit(1)
        port = next_port

    # Spawn background server process (self-fork)
    exe_path = sys.executable
    if getattr(sys, "frozen", False):
        cmd = [exe_path, "--server", "--port", str(port)]
    else:
        script_path = str(Path(__file__).resolve())
        cmd = [sys.executable, script_path, "--server", "--port", str(port)]

    # Windows specific flag to start a detached background process with no window
    CREATE_NO_WINDOW = 0x08000000
    try:
        release_mutex()
        background_proc = subprocess.Popen(cmd, creationflags=CREATE_NO_WINDOW)
    except Exception as e:
        print(f"[오류] 백그라운드 서버 실행 실패: {e}")
        time.sleep(3)
        sys.exit(1)

    # Wait and check if the port is now occupied by the server (poll for up to 10 seconds)
    server_started, early_exit_code = wait_for_background_start(background_proc, port)

    if not server_started:
        if early_exit_code is not None:
            print(f"[오류] 백그라운드 서버가 조기 종료되었습니다. 종료 코드: {early_exit_code}")
        print("[오류] 서버 기동 실패. 백그라운드 프로세스가 정상 시작되지 않았습니다.")
        time.sleep(3)
        sys.exit(1)

    print("=" * 60)
    print("  쉼(SHIM) 연차 관리 시스템 구동 완료!")
    print("=" * 60)
    print(f"  - 접속 주소: http://localhost:{port}")
    print("  - (웹 브라우저를 열고 위 주소를 입력하여 접속하세요.)")
    print("-" * 60)
    print("  ※ 이 창을 닫거나 아무 키나 눌러 종료해도 SHIM 서비스는")
    print("     백그라운드에서 계속 정상적으로 동작합니다.")
    print("  ※ 서비스를 완전히 종료하려면 stop_portable.bat을 실행하세요.")
    print("=" * 60)
    print()

    print("아무 키나 누르면 이 안내 창이 닫힙니다...")
    # Clear any buffered key hits
    while msvcrt.kbhit():
        msvcrt.getch()
    # Wait for key hit
    while True:
        if msvcrt.kbhit():
            msvcrt.getch()
            break
        time.sleep(0.1)
    sys.exit(0)


if __name__ == "__main__":
    main()
