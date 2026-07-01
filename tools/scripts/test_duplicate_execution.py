import os
import sys
import time
import subprocess
import signal
import socket
import threading

# 프로젝트 루트 경로 확보
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except (OSError, ConnectionRefusedError):
            return False

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def test_duplicate_execution():
    print("=" * 60)
    print("SHIM Mutex-Based Duplicate Execution Prevention Test")
    print("=" * 60)

    # 임시 환경 변수 설정
    os.environ["SHIM_SECRET_KEY"] = "shim_test_secret_key_duplicate_prevention_12345"
    
    import tempfile
    # 임시 격리용 데이터 폴더 바인딩
    temp_data_dir = tempfile.TemporaryDirectory(prefix="shim_dup_test_")
    os.environ["SHIM_DATA_DIR"] = temp_data_dir.name

    # 동적 포트 할당
    port_a = find_free_port()
    port_b = find_free_port()
    while port_b == port_a:
        port_b = find_free_port()

    # 1. 첫 번째 서버 인스턴스 A 기동
    cmd_a = [sys.executable, "-u", "portable/shim_portable.py", "--foreground", "--port", str(port_a)]
    
    print(f"[STEP 1] Starting First Server Instance A on port {port_a}...")
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

    env = os.environ.copy()
    env["PYTHONPATH"] = project_root

    proc_a = subprocess.Popen(
        cmd_a,
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=creation_flags,
        env=env,
        text=True,
        bufsize=1
    )

    # A 서버 부팅 대기 (최대 15초)
    print(f"[STEP 2] Waiting for Instance A to bind to port {port_a}...")
    a_ready = False
    start_time = time.time()
    
    output_a = []
    def read_output_a():
        for line in iter(proc_a.stdout.readline, ''):
            output_a.append(line)
            clean_line = line.strip()
            if clean_line:
                print(f"  [Instance A Log] {clean_line}")

    t_read_a = threading.Thread(target=read_output_a, daemon=True)
    t_read_a.start()

    while time.time() - start_time < 45:
        if is_port_in_use(port_a):
            a_ready = True
            break
        time.sleep(0.2)

    if not a_ready:
        print("[ERROR] Instance A failed to start in time.")
        proc_a.kill()
        sys.exit(1)
        
    print("[SUCCESS] Instance A is running and has acquired the Mutex.")

    # 2. 두 번째 서버 인스턴스 B 기동 시도
    # 동일 경로이므로 Mutex가 충돌해야 하며, 포트를 다르게 주더라도 기동에 실패하고 즉각 안전하게 조용히 꺼져야 합니다!
    cmd_b = [sys.executable, "-u", "portable/shim_portable.py", "--foreground", "--port", str(port_b)]
    
    print(f"\n[STEP 3] Starting Second Server Instance B on port {port_b} (expecting duplicate block)...")
    
    proc_b = subprocess.Popen(
        cmd_b,
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=creation_flags,
        env=env,
        text=True,
        bufsize=1
    )

    output_b = []
    def read_output_b():
        for line in iter(proc_b.stdout.readline, ''):
            output_b.append(line)
            clean_line = line.strip()
            if clean_line:
                print(f"  [Instance B Log] {clean_line}")

    t_read_b = threading.Thread(target=read_output_b, daemon=True)
    t_read_b.start()

    # B 프로세스는 중복 실행 제어로 인해 수 초 내에 스스로 즉시 종료되어야 합니다.
    print("[STEP 4] Waiting for Instance B to terminate automatically...")
    try:
        proc_b.wait(timeout=5)
        print(f"[SUCCESS] Instance B terminated automatically with exit code: {proc_b.returncode}")
    except subprocess.TimeoutExpired:
        print("[FAIL] Instance B did not terminate. Mutex guard is not working!")
        proc_b.kill()
        proc_a.kill()
        sys.exit(1)

    # 3. 인스턴스 B 기동 결과 및 A의 생존 확인
    print("\n[STEP 5] Verifying system state...")
    b_exit_code = proc_b.returncode
    a_alive = proc_a.poll() is None
    port_b_in_use = is_port_in_use(port_b)
    
    print(f"  - Instance B exit code: {b_exit_code} (Expected: 0)")
    print(f"  - Instance A is still alive: {a_alive} (Expected: True)")
    print(f"  - Port {port_b} is in use: {port_b_in_use} (Expected: False)")
 
    # 4. A 인스턴스 안전 종료
    print("\n[STEP 6] Cleaning up Instance A...")
    if sys.platform == "win32":
        proc_a.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        proc_a.send_signal(signal.SIGINT)
 
    try:
        proc_a.wait(timeout=5)
        print("[SUCCESS] Instance A terminated cleanly.")
    except subprocess.TimeoutExpired:
        proc_a.kill()
        print("[WARNING] Instance A was force killed.")
 
    test_passed = (b_exit_code == 0) and a_alive and (not port_b_in_use)
    
    print("\n" + "=" * 60)
    print("MUTEX DUPLICATE PREVENTION TEST REPORT")
    print("=" * 60)
    print(f"Instance B Blocked & Exited Cleanly (Code 0): {b_exit_code == 0}")
    print(f"Instance A Survived Collision: {a_alive}")
    print(f"Port {port_b} Unused (B Blocked): {not port_b_in_use}")
    print(f"Overall Result: {'PASSED' if test_passed else 'FAILED'}")
    print("=" * 60)

    temp_data_dir.cleanup()
    return test_passed

if __name__ == "__main__":
    success = test_duplicate_execution()
    sys.exit(0 if success else 1)
