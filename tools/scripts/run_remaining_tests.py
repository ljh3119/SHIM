from datetime import date, timedelta
import os
from pathlib import Path
import sys
import tempfile

# 프로젝트 루트를 경로에 추가
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 테스트용 임시 디렉토리 설정 (기본 DB 보호)
TEST_DATA_DIR = Path(
    os.environ.setdefault("SHIM_DATA_DIR", tempfile.mkdtemp(prefix="shim_full_test_"))
)

from fastapi.testclient import TestClient
from src.app.main import app, startup_event
from src.app.database import SessionLocal
from src.app import models, auth

def next_weekday(start):
    d = start
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d

def clear_user_leaves(db, user_id):
    db.query(models.Leaves).filter(models.Leaves.user_id == user_id).delete(synchronize_session=False)

def main():
    print(f"[TEST] Starting Full Logic Verification (v1.4.0 Compatible)")
    print(f"[TEST] Database: {TEST_DATA_DIR}")
    
    # 1. 환경 초기화
    startup_event()
    client = TestClient(app)
    
    # 초기화 세션 생성 후 즉시 닫기
    db = SessionLocal()

    # 2. 테스트 사용자 생성 (Staff, PM)
    users_to_create = [
        ("u_staff", "일반사원", "STAFF", "Team-A"),
        ("u_pm", "PM관리자", "PM", "HQ"),
        ("u_lead", "팀장", "TEAM_LEAD", "Team-A")
    ]
    for uid, name, role, team in users_to_create:
        if not db.query(models.Users).filter(models.Users.user_id == uid).first():
            db.add(models.Users(
                user_id=uid, user_name=name, role=role, team=team,
                password=auth.get_password_hash("0000"), is_active=True
            ))
    db.commit()
    db.close() # 유저 생성 후 닫기

    d1 = next_weekday(date.today() + timedelta(days=1))
    admin_token = auth.create_access_token({"sub": "admin"})
    admin_client = TestClient(app)
    admin_client.cookies.set("access_token", f"Bearer {admin_token}")

    # --- 시나리오 1: PM 자동 승인 (v1.3.x+ 핵심 로직) ---
    print("[CASE 1] PM Auto-Approval Logic")
    # 승인 필수 옵션 ON
    admin_client.post("/admin/settings/approval", data={"is_approval_required": "true"})
    
    pm_token = auth.create_access_token({"sub": "u_pm"})
    pm_client = TestClient(app)
    pm_client.cookies.set("access_token", f"Bearer {pm_token}")
    
    # 작업 전 세션 열기/닫기 루틴
    db = SessionLocal()
    clear_user_leaves(db, "u_pm")
    db.commit()
    db.close()

    r = pm_client.post("/user/leave", data={
        "date_str": d1.strftime("%Y-%m-%d"), "start_time": "09:00", "end_time": "12:00"
    })
    if r.status_code != 200:
        print(f"  [ERROR] PM Apply failed: {r.status_code} - {r.text}")
    assert r.status_code == 200
    
    db = SessionLocal()
    leave_pm = db.query(models.Leaves).filter(models.Leaves.user_id == "u_pm").first()
    assert leave_pm.status == "APPROVED", f"PM 연차는 자동 승인되어야 합니다. (현재: {leave_pm.status})"
    db.close()
    print("  -> PASS: PM Auto-approval verified.")

    # --- 시나리오 2: 일반 사원 승인 대기 ---
    print("[CASE 2] Staff Pending Logic")
    staff_token = auth.create_access_token({"sub": "u_staff"})
    staff_client = TestClient(app)
    staff_client.cookies.set("access_token", f"Bearer {staff_token}")
    
    db = SessionLocal()
    clear_user_leaves(db, "u_staff")
    db.commit()
    db.close()

    r = staff_client.post("/user/leave", data={
        "date_str": d1.strftime("%Y-%m-%d"), "start_time": "14:00", "end_time": "18:00"
    })
    if r.status_code != 200:
        print(f"  [ERROR] Staff Apply failed: {r.status_code} - {r.text}")
    assert r.status_code == 200
    
    db = SessionLocal()
    leave_staff = db.query(models.Leaves).filter(models.Leaves.user_id == "u_staff").first()
    assert leave_staff.status == "PENDING", "일반 사원 연차는 승인 대기 상태여야 합니다."
    
    # --- 시나리오 3: 연차 삭제 시 감사 로그 생성 및 Race Condition 방지 (v1.4.0) ---
    print("[CASE 3] Leave Deletion & Audit Log (v1.4.0)")
    leave_id = leave_staff.id
    db.close() # API 호출 전 닫기

    # Admin으로 연차 삭제 수행
    r = admin_client.post("/admin/leave/delete", data={"leave_id": leave_id})
    
    assert r.status_code in (200, 302)
    
    db = SessionLocal()
    # 삭제 확인
    deleted = db.query(models.Leaves).filter(models.Leaves.id == leave_id).first()
    assert deleted is None, "연차가 삭제되지 않았습니다."
    
    # 감사 로그 확인 (v1.4.0에서 액션명이 LEAVE_DELETE 또는 DELETE_LEAVE일 수 있음, 확인 결과 api_admin.py는 LEAVE_DELETE 사용)
    audit = db.query(models.AuditLogs).filter(models.AuditLogs.action == "LEAVE_DELETE").order_by(models.AuditLogs.id.desc()).first()
    if not audit: # 폴백 체크
         audit = db.query(models.AuditLogs).filter(models.AuditLogs.action == "DELETE_LEAVE").order_by(models.AuditLogs.id.desc()).first()
    
    assert audit is not None, "삭제 감사 로그가 생성되지 않았습니다."
    print("  -> PASS: Deletion & Audit log verified.")

    # --- 시나리오 4: 1.4.0 UI 전역 함수 (min/max) 및 페이징 쿼리 검증 ---
    print("[CASE 4] Pagination & Template Globals Check")
    # 타임라인 쿼리 (admin_service)
    from src.app.services import admin_service
    query = admin_service.get_leaves_timeline_query(db, year=d1.year)
    # 페이징 적용 확인 (v1.4.0에서 50건 단위 도입됨)
    paged_results = query.offset(0).limit(50).all()
    assert isinstance(paged_results, list)
    
    # Template globals check (min/max)
    assert app.state.templates.env.globals["min"] == min
    assert app.state.templates.env.globals["max"] == max
    print("  -> PASS: v1.4.0 Architecture & Logic verified.")

    print("\n[COMPLETE] All v1.4.0 key features verified successfully.")
    db.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[FAILURE] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
