import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.app.database import engine, DB_PATH
from src.app import models
from src.app.services.ops import verify_and_recover_db
from src.app.migrations import run_all_migrations

class DBInitLock:
    """원자적 디렉터리 생성을 활용한 파일 시스템 기반 분산 락"""
    def __init__(self, lock_dir_path: Path, timeout: int = 45):
        self.lock_dir = lock_dir_path
        self.timestamp_file = lock_dir_path / "lock.time"
        self.timeout = timeout

    def __enter__(self):
        start = time.time()
        while True:
            try:
                # 원자적 디렉터리 생성 (OS 수준에서 중복 생성 시 FileExistsError 발생시킴)
                self.lock_dir.mkdir(exist_ok=False)
                # 락을 쥔 시점의 타임스탬프 영구 보관 (고아 락 방어 목적)
                self.timestamp_file.write_text(str(time.time()), encoding="utf-8")
                print(f"[DBLock] 초기화 독점 잠금 획득 성공 ({self.lock_dir})")
                return self
            except FileExistsError:
                # 이미 락 디렉터리가 존재하는 경우 -> 고아 락 만료 시간(10분) 초과 체크
                if self.timestamp_file.exists():
                    try:
                        created_time = float(self.timestamp_file.read_text(encoding="utf-8").strip())
                        if time.time() - created_time > 600.0:
                            print("[DBLock] 만료된 이전 고아 DBLock을 감지하여 강제 제거합니다.")
                            self.release()
                            continue
                    except ValueError:
                        pass
                
                # 획득 재시도 및 타임아웃
                if time.time() - start > self.timeout:
                    raise TimeoutError(
                        f"DB 마이그레이션 락 대기 시간 초과 ({self.timeout}초). "
                        "타 노드가 데이터베이스를 초기화 중이거나 잠금이 고립되었습니다."
                    )
                time.sleep(0.5)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def release(self):
        """디렉터리 및 타임스탬프 파일을 제거하여 락 해제"""
        if self.timestamp_file.exists():
            try:
                self.timestamp_file.unlink()
            except FileNotFoundError:
                pass
        if self.lock_dir.exists():
            try:
                self.lock_dir.rmdir()
                print("[DBLock] 초기화 독점 잠금 해제 완료")
            except FileNotFoundError:
                pass

def init_db():
    lock_path = DB_PATH.parent / "migration.lock"
    with DBInitLock(lock_path):
        print("[DB_INIT] Verifying and recovering SQLite database if needed...")
        verify_and_recover_db(DB_PATH)
        
        print("[DB_INIT] Creating database tables...")
        models.Base.metadata.create_all(bind=engine)
        
        print("[DB_INIT] Running schema migrations...")
        try:
            run_all_migrations(engine)
            
            print("[DB_INIT] Database initialization successfully completed.")
        except Exception as e:
            print(f"[DB_INIT ERROR] Schema migration failed: {e}")
            sys.exit(1)

if __name__ == "__main__":
    init_db()
