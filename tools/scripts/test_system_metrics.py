import os
import tempfile
from pathlib import Path
import sys
import datetime

# 프로젝트 루트를 경로에 추가
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 테스트용 임시 디렉토리 설정 (기본 DB 보호)
TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="shim_metrics_test_"))
os.environ["SHIM_DATA_DIR"] = str(TEST_DATA_DIR)

from fastapi.testclient import TestClient
from src.app.main import app, startup_event
from src.app.database import SessionLocal, DB_PATH
from src.app import models, utils, database
from src.app.services import ops

def test_metrics():
    print("[TEST] Starting System Metrics & Background Status Verification")
    
    # 1. DB 초기화 및 구동
    from tools.scripts.db_init import init_db
    init_db()
    startup_event()
    
    client = TestClient(app)
    
    db = SessionLocal()
    try:
        # 최초 Settings 상태 점검
        settings = db.query(models.SystemSettings).first()
        assert settings is not None, "SystemSettings가 생성되지 않았습니다."
        assert settings.last_db_size_kb is not None and settings.last_db_size_kb >= 0
        assert settings.last_backup_count is not None and settings.last_backup_count >= 0
        
        initial_db_size = settings.last_db_size_kb
        initial_backup_count = settings.last_backup_count
        print(f"  Initial DB size: {initial_db_size} KB, Backup count: {initial_backup_count}")
        
        # 2. update_system_metrics_in_db 직접 실행 테스트
        ops.update_system_metrics_in_db(db)
        settings_after = db.query(models.SystemSettings).first()
        assert settings_after.last_db_size_kb is not None
        
        # 3. 백업 스케줄러 메트릭 연동 테스트
        # run_backup_and_rotate 실행 후 DB 업데이트 확인
        backup_path = ops.run_backup_and_rotate(DB_PATH, max_backups=2)
        assert backup_path is not None, "백업 생성 실패"
        assert backup_path.exists()
        
        # 백업 후 DB 재조회
        db.expire_all()
        settings_after_backup = db.query(models.SystemSettings).first()
        assert settings_after_backup.last_backup_time is not None, "최종 백업 시간 업데이트 실패"
        assert settings_after_backup.last_backup_count > 0, "최종 백업 개수 업데이트 실패"
        print(f"  Backup metrics updated - Time: {settings_after_backup.last_backup_time}, Count: {settings_after_backup.last_backup_count}")
        
        # 백업 정리
        if backup_path.exists():
            backup_path.unlink()
            
        # 4. 알림 정리 스케줄러 메트릭 연동 테스트
        ops.cleanup_old_notifications()
        db.expire_all()
        settings_after_cleanup = db.query(models.SystemSettings).first()
        assert settings_after_cleanup.last_cleanup_time is not None, "최종 알림 정리 시간 업데이트 실패"
        print(f"  Cleanup metrics updated - Time: {settings_after_cleanup.last_cleanup_time}")
        
        # 5. 대시보드 API 응답의 system_metrics 검증
        # 로그인 수행 (Admin 권한 필요)
        from src.app import auth
        admin_token = auth.create_access_token({"sub": "admin"})
        client.cookies.set("access_token", f"Bearer {admin_token}")
        
        r = client.get("/admin/dashboard")
        assert r.status_code == 200
        html_text = r.text
        assert "시스템 운영 현황" in html_text
        assert "활성 사원" in html_text
        assert "가동 시간" in html_text
        assert "DB 용량" in html_text
        assert "PII 보안" in html_text
        assert "최종 자동 백업" in html_text
        assert "최종 알림 정리" in html_text
        print("  -> PASS: Dashboard UI metrics rendering verified.")
        
        # 6. 임계치 초과 헬스체크(26시간 지연 경고) 시뮬레이션
        # 백업 시각을 30시간 전으로 강제 업데이트
        past_time = utils.get_local_now() - datetime.timedelta(hours=30)
        settings_after_cleanup.last_backup_time = past_time
        db.commit()
        
        r_warning = client.get("/admin/dashboard")
        assert r_warning.status_code == 200
        assert "지연/점검필요" in r_warning.text, "26시간 지연 시 경고 뱃지가 노출되어야 합니다."
        print("  -> PASS: Health threshold (26 hours) warning badge verified.")
        
    finally:
        db.close()
        # 임시 디렉토리 정리
        database.engine.dispose()
        import shutil
        try:
            shutil.rmtree(TEST_DATA_DIR)
        except Exception:
            pass

if __name__ == "__main__":
    test_metrics()
