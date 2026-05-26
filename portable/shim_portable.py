import os
import sys
from pathlib import Path
import socket
import subprocess
import time
import argparse
import msvcrt
import ctypes
from ctypes import wintypes
import threading
import webbrowser

import uvicorn

# --- Native Windows System Tray Support via ctypes ---
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

_current_port = 8000
_nid = NOTIFYICONDATAW()
_hwnd = None
_uvicorn_proc = None

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
    
    # 3. Uvicorn 자식 프로세스에게 CTRL_BREAK_EVENT 송신
    global _uvicorn_proc
    if _uvicorn_proc:
        try:
            import signal
            _uvicorn_proc.send_signal(signal.CTRL_BREAK_EVENT)
            _uvicorn_proc.wait(timeout=2.0)
        except Exception as e:
            print(f"[오류] 자식 프로세스 종료 시그널 전송 실패: {e}")
    
    # 4. 트레이 자원 반환 및 메시지 루프 종료
    cleanup_tray_icon(hwnd)
    user32.PostQuitMessage(0)
    os._exit(0)

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

def run_tray_icon_thread(port):
    global _current_port, _nid, _hwnd, _wndproc_delegate
    _current_port = port

    wc = WNDCLASSW()
    wc.lpfnWndProc = _wndproc_delegate
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = "SHIMTrayClass"
    user32.RegisterClassW(ctypes.byref(wc))
    
    hwnd = user32.CreateWindowExW(
        0, wc.lpszClassName, "SHIM Tray Window",
        0, 0, 0, 0, 0, None, None, wc.hInstance, None
    )
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
    
    shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(_nid))
    
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

        # 비밀번호를 '0000'으로 초기화
        new_hash = auth.get_password_hash("0000")
        admin.password = new_hash
        
        # 감사 로그 기록 (누가 했는지 알 수 없으므로 시스템 초기화 목적을 밝혀 'admin' 계정 ID로 기록)
        db.add(models.AuditLogs(
            actor_id="admin",
            action="RESET_ADMIN_PASSWORD",
            target_info="Admin:admin",
            old_data="*****",
            new_data="0000 (Emergency Reset)"
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
            mutex_name = f"Global\\SHIM_Portable_Mutex_{h}"
            
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
            from src.app.main import app as fastapi_app
            uvicorn.run(fastapi_app, host="0.0.0.0", port=port, reload=False)
        except KeyboardInterrupt:
            pass
        sys.exit(0)

    if args.server:
        # Background Server Instance (Master process managing tray icon and worker process)
        port = args.port if args.port else 8000
        os.environ["SHIM_PORT"] = str(port)

        # Start native system tray thread
        t = threading.Thread(target=run_tray_icon_thread, args=(port,), daemon=True)
        t.start()

        # Spawn uvicorn worker process
        exe_path = sys.executable
        if getattr(sys, "frozen", False):
            cmd = [exe_path, "--uvicorn-worker", "--port", str(port)]
        else:
            script_path = str(Path(__file__).resolve())
            cmd = [sys.executable, script_path, "--uvicorn-worker", "--port", str(port)]

        # CREATE_NEW_PROCESS_GROUP = 0x00000200, CREATE_NO_WINDOW = 0x08000000
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000
        
        global _uvicorn_proc
        try:
            _uvicorn_proc = subprocess.Popen(cmd, creationflags=flags)
            _uvicorn_proc.wait()
        except KeyboardInterrupt:
            # Handle SIGINT to shutdown graceful
            if _uvicorn_proc:
                try:
                    import signal
                    _uvicorn_proc.send_signal(signal.CTRL_BREAK_EVENT)
                    _uvicorn_proc.wait(timeout=2.0)
                except Exception:
                    pass
        finally:
            if _hwnd:
                cleanup_tray_icon(_hwnd)
        sys.exit(0)

    if args.foreground:
        # Foreground Interactive Instance
        port = args.port if args.port else resolve_port(8000)
        os.environ["SHIM_PORT"] = str(port)
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
        subprocess.Popen(cmd, creationflags=CREATE_NO_WINDOW)
    except Exception as e:
        print(f"[오류] 백그라운드 서버 실행 실패: {e}")
        time.sleep(3)
        sys.exit(1)

    # Wait and check if the port is now occupied by the server (poll for up to 10 seconds)
    server_started = False
    for _ in range(20): # 20 * 0.5s = 10s
        time.sleep(0.5)
        if is_port_in_use(port):
            server_started = True
            break

    if not server_started:
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
