import os
import sys
import time
import subprocess
import signal
import threading
import socket

# 프로젝트 루트 경로 확보
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    import requests
except ImportError:
    print("[ERROR] 'requests' package is required to run this graceful shutdown test.")
    print("Please install development dependencies using: pip install -r requirements-dev.txt")
    sys.exit(1)

# 임시 DB 및 환경 설정
os.environ["SHIM_PORT"] = "8099"
os.environ["SHIM_SECRET_KEY"] = "shim_test_secret_key_graceful_shutdown_12345"
os.environ["SHIM_DATA_DIR"] = os.path.abspath(os.path.join(project_root, "var/data_test_shutdown"))

db_dir = os.environ["SHIM_DATA_DIR"]
db_file = os.path.join(db_dir, "shim_internal.db")
db_wal = db_file + "-wal"
db_shm = db_file + "-shm"

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except (OSError, ConnectionRefusedError):
            return False


def clean_db_files():
    for f in [db_file, db_wal, db_shm]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception as e:
                print(f"[CLEANUP ERROR] Failed to remove {f}: {e}")

def run_background_requests(stop_event):
    # 서버 기동 후 API 호출을 지속적으로 날려서 트랜잭션/세션 처리를 유도
    session = requests.Session()
    while not stop_event.is_set():
        try:
            session.get("http://localhost:8099/", timeout=1)
        except requests.exceptions.RequestException:
            pass
        time.sleep(0.1)

def test_graceful_shutdown():
    print("=" * 60)
    print("SHIM Graceful Shutdown & DB Teardown Automation Test")
    print("=" * 60)

    # 1. 이전 잔여 파일 정리
    clean_db_files()

    # 2. 서버 실행 명령 준비 (비대화형 테스트 환경 호환을 위해 --foreground 모드로 구동)
    cmd = [sys.executable, "-u", "portable/shim_portable.py", "--foreground", "--port", "8099"]
    
    print("[STEP 1] Starting SHIM Server in foreground mode (Process Group)...")
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

    env = os.environ.copy()
    env["PYTHONPATH"] = project_root

    process = subprocess.Popen(
        cmd,
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=creation_flags,
        env=env,
        text=True,
        bufsize=1
    )


    # 서버 부팅 대기 (최대 15초)
    print("[STEP 2] Waiting for server to bind to port 8099...")
    server_ready = False
    start_time = time.time()
    
    # stdout을 비차단식으로 모니터링하여 로그 수집
    output_lines = []
    def read_output():
        for line in iter(process.stdout.readline, ''):
            output_lines.append(line)
            clean_line = line.strip()
            if clean_line:
                print(f"  [Server Log] {clean_line}")

    t_read = threading.Thread(target=read_output, daemon=True)
    t_read.start()

    while time.time() - start_time < 45:
        if is_port_in_use(8099):
            server_ready = True
            break
        time.sleep(0.2)


    if not server_ready:
        print("[ERROR] Server failed to start or bind to port 8099 in time.")
        print("----- Server Console Output -----")
        print("".join(output_lines))
        print("---------------------------------")
        process.kill()
        sys.exit(1)
    
    print("[SUCCESS] SHIM Server started and bound to port 8099.")

    # 3. 요청 스레드 가동
    print("[STEP 3] Launching background API requests during operation...")
    stop_req = threading.Event()
    t_req = threading.Thread(target=run_background_requests, args=(stop_req,))
    t_req.start()
    time.sleep(1.5)  # 1.5초간 요청 발생

    # 4. Graceful Shutdown 시그널 송신
    print("[STEP 4] Sending CTRL_BREAK_EVENT (Graceful Shutdown) to the process group...")
    stop_req.set()
    t_req.join()

    # Windows/Linux 대응 시그널 전송
    if sys.platform == "win32":
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        process.send_signal(signal.SIGINT)

    # 5. 프로세스 종료 대기
    print("[STEP 5] Waiting for process to terminate and port 8099 to release...")
    try:
        process.wait(timeout=5)
        print(f"[SUCCESS] Server process terminated with exit code: {process.returncode}")
    except subprocess.TimeoutExpired:
        print("[WARNING] Process did not terminate in time. Force killing...")
        process.kill()
        process.wait()

    # 포트 해제 대기
    port_released = False
    for _ in range(25):
        if not is_port_in_use(8099):
            port_released = True
            break
        time.sleep(0.2)

    # 6. DB 정리 상태 분석
    print("[STEP 6] Analyzing DB lock files (.db-wal, .db-shm)...")
    time.sleep(1.0) # OS 파일 락 해제 대기
    
    wal_exists = os.path.exists(db_wal)
    shm_exists = os.path.exists(db_shm)
    
    print(f"  - Database main file exists: {os.path.exists(db_file)}")
    print(f"  - WAL file exists: {wal_exists}")
    print(f"  - SHM file exists: {shm_exists}")

    log_check = any("Lifespan shutdown: Database connection pool disposed successfully" in l for l in output_lines)
    db_clean = not wal_exists and not shm_exists
    
    print("\n" + "=" * 60)
    print("GRACEFUL SHUTDOWN TEST REPORT")
    print("=" * 60)
    print(f"Lifespan Shutdown Log Detected: {log_check}")
    print(f"Port 8099 Released: {port_released}")
    print(f"WAL/SHM Files Cleanly Merged: {db_clean}")
    
    # 7. 사후 정리
    clean_db_files()

    if port_released and db_clean and log_check:
        print("[SUCCESS] Graceful shutdown test PASSED.")
        return True
    else:
        print("[FAIL] Graceful shutdown test FAILED.")
        return False

if __name__ == "__main__":
    success = test_graceful_shutdown()
    sys.exit(0 if success else 1)
