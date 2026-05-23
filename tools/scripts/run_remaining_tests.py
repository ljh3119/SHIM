from datetime import date, timedelta
import os
from pathlib import Path
import sys
import tempfile
import asyncio

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

def next_business_day(start, db):
    d = start
    while True:
        if d.weekday() >= 5:
            d += timedelta(days=1)
            continue
        is_holiday = db.query(models.Holidays).filter(models.Holidays.date == d).first()
        if is_holiday:
            d += timedelta(days=1)
            continue
        break
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
    d1 = next_business_day(date.today() + timedelta(days=1), db)
    db.commit()
    db.close() # 유저 생성 후 닫기
    admin_token = auth.create_access_token({"sub": "admin"})
    admin_client = TestClient(app)
    admin_client.cookies.set("access_token", f"Bearer {admin_token}")

    # --- 시나리오 1: PM 자동 승인 (v1.3.x+ 핵심 로직) ---
    print("[CASE 1] PM Auto-Approval Logic")
    # 승인 필수 옵션 ON
    admin_client.post("/api/admin/settings/approval", data={"is_approval_required": "true"})
    
    pm_token = auth.create_access_token({"sub": "u_pm"})
    pm_client = TestClient(app)
    pm_client.cookies.set("access_token", f"Bearer {pm_token}")
    
    # 작업 전 세션 열기/닫기 루틴
    db = SessionLocal()
    clear_user_leaves(db, "u_pm")
    db.commit()
    db.close()

    r = pm_client.post("/api/user/leave", data={
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

    r = staff_client.post("/api/user/leave", data={
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

    # [검증] 공가 전환 후 연차 복구 전환 시 에러 여부 검증
    # 1) 공가(비차감)로 전환
    r_to_public = admin_client.post("/api/admin/leave/update-type", data={"leave_id": leave_id, "is_deductive": "false"})
    assert r_to_public.status_code == 200
    db = SessionLocal()
    leave_checked = db.query(models.Leaves).filter(models.Leaves.id == leave_id).first()
    assert leave_checked.is_deductive is False, "공가 전환 실패"
    db.close()

    # 2) 다시 연차(차감)로 복구 전환
    r_to_deduct = admin_client.post("/api/admin/leave/update-type", data={"leave_id": leave_id, "is_deductive": "true"})
    assert r_to_deduct.status_code == 200
    db = SessionLocal()
    leave_checked = db.query(models.Leaves).filter(models.Leaves.id == leave_id).first()
    assert leave_checked.is_deductive is True, "연차 전환 실패"

    # 3) 감사 로그 기록 검증
    audit_type = db.query(models.AuditLogs).filter(models.AuditLogs.action == "UPDATE_LEAVE_TYPE").order_by(models.AuditLogs.id.desc()).first()
    assert audit_type is not None, "휴가 유형 변경 감사 로그 누락"
    assert "is_deductive=True" in audit_type.new_data
    db.close()

    # Admin으로 연차 삭제 수행
    r = admin_client.post("/api/admin/leave/delete", data={"leave_id": leave_id})
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

    # --- 시나리오 5: 전사 캘린더 공유 활성화 및 권한 검증 ---
    print("[CASE 5] Company Calendar Sharing & Access Control")
    
    # 1. 캘린더 공유 범위를 '소속 팀원 공유 (team)'로 변경
    admin_client.post("/api/admin/settings/calendar-scope", data={"scope": "team"})
    
    from src.app.routers.api_user import user_team_calendar
    from unittest.mock import MagicMock
    
    # 가짜 Request 객체 생성
    req = MagicMock()
    req.url.path = "/user/team-calendar"
    req.app.state.templates = app.state.templates
    
    from src.app.routers import api_user as api_user_module
    orig_get_current_user = api_user_module.get_current_user
    
    db = SessionLocal()
    staff_user = db.query(models.Users).filter(models.Users.user_id == "u_staff").first()
    db.close()
    
    # 1-1. scope=team 일 때 (본인 팀원만 조회되어야 함)
    api_user_module.get_current_user = lambda r, d: staff_user
    db = SessionLocal()
    resp = user_team_calendar(request=req, db=db, user=staff_user)
    context = resp.context
    members = context["team_members"]
    member_ids = [m.user_id for m in members]
    assert "u_staff" in member_ids
    assert "u_lead" in member_ids
    assert "u_pm" not in member_ids, f"팀원 캘린더 공유 상태에서 다른 팀원(PM)이 조회되면 안 됩니다. (조회 목록: {member_ids})"
    db.close()
    
    # 2. 캘린더 공유 범위를 '전사 공유 (company)'로 변경
    r = admin_client.post("/api/admin/settings/calendar-scope", data={"scope": "company"})
    assert r.status_code == 200
    
    # 2-1. 감사 로그 생성 검증
    db = SessionLocal()
    audit_setting = db.query(models.AuditLogs).filter(models.AuditLogs.action == "UPDATE_CALENDAR_SCOPE_SETTING").order_by(models.AuditLogs.id.desc()).first()
    assert audit_setting is not None, "캘린더 공유 범위 변경 감사 로그가 생성되지 않았습니다."
    assert audit_setting.new_data == "company"
    db.close()
    
    # 2-2. scope=company 일 때 (전사 사원 모두 조회되어야 함)
    db = SessionLocal()
    resp = user_team_calendar(request=req, db=db, user=staff_user)
    context = resp.context
    members = context["team_members"]
    member_ids = [m.user_id for m in members]
    assert "u_staff" in member_ids
    assert "u_lead" in member_ids
    assert "u_pm" in member_ids, f"전사 캘린더 공유 활성화 시 다른 팀원(PM)도 조회되어야 합니다. (조회 목록: {member_ids})"
    db.close()
 
    # 3. 캘린더 공유 범위를 '공유 안 함 (none)'으로 변경
    r = admin_client.post("/api/admin/settings/calendar-scope", data={"scope": "none"})
    assert r.status_code == 200
    
    # 3-1. 리다이렉트 응답 확인
    db = SessionLocal()
    resp = user_team_calendar(request=req, db=db, user=staff_user)
    assert resp.status_code == 302
    assert resp.headers.get("location") == "/user/dashboard"
    db.close()
    
    # 원래대로 복구
    api_user_module.get_current_user = orig_get_current_user
    print("  -> PASS: Company Calendar Sharing & Access Control verified.")

    # --- 시나리오 6: 다수일 일괄 신청 및 롤백 검증 (v1.5.0) ---
    print("[CASE 6] Bulk Leave Application & Rollback (v1.5.0)")
    
    # 점심시간 설정 변경 (12:00 ~ 13:00)
    admin_client.post("/api/admin/settings/time-policy", data={
        "time_granularity_minutes": 60,
        "work_start_minute": 540,
        "work_end_minute": 1080,
        "lunch_start_minute": 720,
        "lunch_end_minute": 780
    })
    
    # u_staff의 기존 연차 삭제
    db = SessionLocal()
    clear_user_leaves(db, "u_staff")
    db.commit()
    db.close()
    
    # 2026-06-08(월) ~ 2026-06-14(일) 중 평일: 5일 (08, 09, 10, 11, 12). 주말: 13, 14
    # 콤마로 구분된 날짜 리스트 (주말인 13, 14를 포함시킴)
    bulk_dates = "2026-06-08,2026-06-09,2026-06-10,2026-06-11,2026-06-12,2026-06-13,2026-06-14"
    
    r = staff_client.post("/api/user/leave", data={
        "date_str": bulk_dates, "start_time": "09:00", "end_time": "18:00"
    })
    
    assert r.status_code == 200, f"일괄 신청 실패: {r.text}"
    
    # DB 확인: 6월 13일(토), 14일(일)은 스킵되고 평일 5개만 등록되어야 함.
    db = SessionLocal()
    leaves = db.query(models.Leaves).filter(models.Leaves.user_id == "u_staff").all()
    assert len(leaves) == 5, f"평일 5일만 등록되어야 하는데 {len(leaves)}개가 등록되었습니다."
    
    # 감사 로그 확인
    audit_bulk = db.query(models.AuditLogs).filter(models.AuditLogs.action == "APPLY_LEAVE_BULK").order_by(models.AuditLogs.id.desc()).first()
    assert audit_bulk is not None, "일괄 신청 감사 로그가 없습니다."
    assert "Leaves for 2026-06-" in audit_bulk.target_info, "감사 로그 타겟 정보 확인 실패"
    
    # 롤백 검증: 기존 등록된 6월 8일이 중복되도록 새로운 일괄 신청
    # 2026-06-08(중복), 2026-06-15(미등록) 신청
    r_dup = staff_client.post("/api/user/leave", data={
        "date_str": "2026-06-08,2026-06-15", "start_time": "09:00", "end_time": "18:00"
    })
    
    assert r_dup.status_code == 400, "중복 신청이 포함되었는데 에러가 발생하지 않았습니다."
    
    # 2026-06-15가 등록되지 않았는지 확인 (롤백 여부)
    leave_15 = db.query(models.Leaves).filter(
        models.Leaves.user_id == "u_staff", 
        models.Leaves.date == date(2026, 6, 15)
    ).first()
    assert leave_15 is None, "롤백이 수행되지 않아 2026-06-15 연차가 등록되었습니다."
    
    # --- v1.5.1 추가 검증: 시간 생략 전송 (자동 하루종일 매핑) ---
    clear_user_leaves(db, "u_staff")
    db.commit()
    
    # 1) 다수일 일괄 신청 시 시간 생략
    r_all_day_bulk = staff_client.post("/api/user/leave", data={
        "date_str": "2026-06-08,2026-06-09",
        "start_time": "",
        "end_time": ""
    })
    assert r_all_day_bulk.status_code == 200, f"시간 생략 다수일 신청 실패: {r_all_day_bulk.text}"
    
    leaves_bulk = db.query(models.Leaves).filter(
        models.Leaves.user_id == "u_staff",
        models.Leaves.date.in_([date(2026, 6, 8), date(2026, 6, 9)])
    ).all()
    assert len(leaves_bulk) == 2
    for lv in leaves_bulk:
        assert lv.snapshot_deduction_hours == 8.0, f"예상 차감 시간: 8.0, 실제: {lv.snapshot_deduction_hours}"
        assert lv.snapshot_start_min == 540, f"예상 시작 분: 540, 실제: {lv.snapshot_start_min}"
        assert lv.snapshot_end_min == 1080, f"예상 종료 분: 1080, 실제: {lv.snapshot_end_min}"
        
    clear_user_leaves(db, "u_staff")
    db.commit()
    
    # 2) 단일 날짜 신청 시 시간 생략 (하루종일 체크박스 전송 시나리오)
    r_all_day_single = staff_client.post("/api/user/leave", data={
        "date_str": "2026-06-08",
        "start_time": "",
        "end_time": ""
    })
    assert r_all_day_single.status_code == 200, f"시간 생략 단일 신청 실패: {r_all_day_single.text}"
    
    leave_single = db.query(models.Leaves).filter(
        models.Leaves.user_id == "u_staff",
        models.Leaves.date == date(2026, 6, 8)
    ).first()
    assert leave_single is not None
    assert leave_single.snapshot_deduction_hours == 8.0
    assert leave_single.snapshot_start_min == 540
    assert leave_single.snapshot_end_min == 1080
    
    db.close()
    print("  -> PASS: Bulk leave application & Rollback verified (including v1.5.1 time-omitted Full-day mapping).")
    
    # --- 시나리오 7: 시스템 설정 인메모리 캐싱 검증 (v1.5.0) ---
    print("[CASE 7] System Settings In-Memory Caching (v1.5.0)")
    
    from src.app.services.leave_policy import get_system_settings
    
    db = SessionLocal()
    # 초기 캐싱 동작 확인
    settings_before = get_system_settings(db)
    initial_title = settings_before.product_display_name
    
    # Admin API를 통한 설정 변경 (Branding 명칭 변경)
    import time
    new_title = f"SHIM-{int(time.time())}"
    # app.css 등을 로드하는 과정에서 캐시 설정이 변경되므로 설정 API에 요청 보냄
    r_setting = admin_client.post("/api/admin/settings/branding", data={
        "product_display_name": new_title,
        "product_nav_short": settings_before.product_nav_short or "",
        "brand_initial": settings_before.brand_initial or ""
    })
    assert r_setting.status_code == 200, "설정 변경 API 호출 실패"
    
    # 캐시가 갱신되어 새로운 타이틀이 나오는지 확인
    settings_after = get_system_settings(db)
    assert settings_after.product_display_name == new_title, f"인메모리 캐시 갱신 실패. (예상: {new_title}, 실제: {settings_after.product_display_name})"
    db.close()
    print("  -> PASS: System settings cache verified.")

    # --- 시나리오 8: 비밀번호 변경 기능 검증 (자가 변경 및 관리자 변경) ---
    print("[CASE 8] User & Admin Password Self-Service Change")
    
    # 1) 일반 사용자 비밀번호 변경 검증
    # 잘못된 현재 비밀번호 입력 시 실패
    r = staff_client.post("/api/user/change-password", data={
        "current_password": "wrong_password",
        "new_password": "new_password_123"
    })
    assert r.status_code == 400
    assert "현재 비밀번호가 일치하지 않습니다." in r.json()["message"]
    
    # 새 비밀번호 길이 미달(4자 미만) 시 실패
    r = staff_client.post("/api/user/change-password", data={
        "current_password": "0000",
        "new_password": "abc"
    })
    assert r.status_code == 400
    assert "최소 4자 이상" in r.json()["message"]

    # 성공적인 비밀번호 변경
    r = staff_client.post("/api/user/change-password", data={
        "current_password": "0000",
        "new_password": "new_staff_password"
    })
    assert r.status_code == 200
    assert "비밀번호가 성공적으로 변경되었습니다." in r.json()["message"]
    
    # 변경된 비밀번호로 검증
    db = SessionLocal()
    updated_user = db.query(models.Users).filter(models.Users.user_id == "u_staff").first()
    assert auth.verify_password("new_staff_password", updated_user.password)
    
    # 감사 로그(CHANGE_PASSWORD) 확인
    audit_pwd = db.query(models.AuditLogs).filter(
        models.AuditLogs.action == "CHANGE_PASSWORD",
        models.AuditLogs.actor_id == "u_staff"
    ).order_by(models.AuditLogs.id.desc()).first()
    assert audit_pwd is not None
    assert audit_pwd.old_data == "*****"
    assert audit_pwd.new_data == "*****"
    db.close()

    # 2) 관리자 비밀번호 변경 검증
    # 잘못된 현재 비밀번호
    r = admin_client.post("/api/admin/change-password", data={
        "current_password": "wrong_admin_pwd",
        "new_password": "new_admin_pwd_123"
    })
    assert r.status_code == 400
    assert "현재 비밀번호가 일치하지 않습니다." in r.json()["message"]
    
    # 새 비밀번호 길이 미달(4자 미만)
    r = admin_client.post("/api/admin/change-password", data={
        "current_password": "0000",
        "new_password": "123"
    })
    assert r.status_code == 400
    assert "최소 4자 이상" in r.json()["message"]

    # 성공적인 변경
    r = admin_client.post("/api/admin/change-password", data={
        "current_password": "0000",
        "new_password": "new_admin_pwd"
    })
    assert r.status_code == 200
    
    db = SessionLocal()
    updated_admin = db.query(models.Users).filter(models.Users.user_id == "admin").first()
    assert auth.verify_password("new_admin_pwd", updated_admin.password)
    
    # 감사 로그(CHANGE_ADMIN_PASSWORD) 확인
    audit_admin = db.query(models.AuditLogs).filter(
        models.AuditLogs.action == "CHANGE_ADMIN_PASSWORD"
    ).order_by(models.AuditLogs.id.desc()).first()
    assert audit_admin is not None
    assert audit_admin.old_data == "*****"
    assert audit_admin.new_data == "*****"
    db.close()
    
    print("  -> PASS: User & Admin password change verified.")

    # --- 시나리오 9: SQLite 외래 키 제약 조건 및 트랜잭션 롤백 무결성 검증 ---
    print("[CASE 9] SQLite Foreign Key & Rollback Integrity")
    db = SessionLocal()
    # 외래 키 위반 시 유발 검증: 존재하지 않는 user_id인 'non_existent_user'로 Leaves 삽입 시도
    invalid_leave = models.Leaves(
        user_id="non_existent_user", # 존재하지 않는 사용자 ID
        date=date.today(),
        snapshot_slot_label="09:00~18:00",
        snapshot_start_min=540,
        snapshot_end_min=1080,
        snapshot_deduction_hours=8.0,
        status="APPROVED",
        year=date.today().year,
        is_deductive=True
    )
    db.add(invalid_leave)
    from sqlalchemy.exc import IntegrityError
    try:
        db.commit()
        # 실패해야 정상
        assert False, "외래 키 제약 조건 위반 에러가 발생해야 합니다."
    except IntegrityError:
        db.rollback()
        print("  -> PASS: Foreign key validation error and rollback successfully handled.")
    db.close()

    # --- 시나리오 10: 소수점 연차 잔여량 표기 및 유틸리티 정밀성 검증 ---
    print("[CASE 10] Decimal Precision Formatting (utils)")
    from src.app import utils as shim_utils
    # 0.5단위 소수점이 온전히 출력되는지 검증 (반올림으로 뭉개지지 않음)
    assert shim_utils.hours_to_days_hours_compact(7.5) == "7.5h"
    assert shim_utils.hours_to_days_hours_compact(-4.5) == "-4.5h"
    assert shim_utils.hours_to_days_hours_compact(8.0) == "1일"
    assert shim_utils.hours_to_days_hours_compact(12.0) == "1일4h"
    assert shim_utils.hours_to_days_hours_compact(12.5) == "1일4.5h"
    print("  -> PASS: Decimal formatting precision verified.")

    # --- 시나리오 11: JWT 쿠키 보안 설정 및 HTTPS 프로토콜 분기 검증 ---
    print("[CASE 11] JWT Cookie Security Settings")
    # 1. 일반 로그인 응답에서 SameSite=Lax 확인
    cookie_client = TestClient(app)
    r_login = cookie_client.post("/login", data={"user_id": "u_staff", "password": "new_staff_password"}, follow_redirects=False)
    assert r_login.status_code == 302
    cookie_header = r_login.headers.get("set-cookie", "")
    assert "samesite=lax" in cookie_header.lower()
    
    # 2. SHIM_SECURE_COOKIE 활성화 시 Secure=True 주입 검증
    os.environ["SHIM_SECURE_COOKIE"] = "true"
    secure_cookie_client = TestClient(app)
    r_secure_login = secure_cookie_client.post("/login", data={"user_id": "u_staff", "password": "new_staff_password"}, follow_redirects=False)
    cookie_header_sec = r_secure_login.headers.get("set-cookie", "")
    assert "secure" in cookie_header_sec.lower()
    os.environ.pop("SHIM_SECURE_COOKIE", None)
    print("  -> PASS: SameSite=Lax and Secure cookie dynamic flag verified.")

    # --- 시나리오 12: SQLite WAL 백업 기능 동작성 검증 ---
    print("[CASE 12] SQLite WAL Online Backup Operation")
    from src.app.services import ops
    from src.app.database import DB_PATH
    
    backup_dir = TEST_DATA_DIR / "backups"
    
    backup_path = ops.create_sqlite_backup(db_path=DB_PATH, backup_dir=backup_dir)
    assert backup_path.exists(), "백업 파일이 생성되지 않았습니다."
    assert backup_path.stat().st_size > 0, "백업 파일 크기가 0 바이트입니다."
    backup_path.unlink()
    print("  -> PASS: Online backup using sqlite3.backup() completed successfully.")

    # --- 시나리오 13: 역할 기반 권한 제어(RBAC) 및 보안 정책 우회 차단 검증 ---
    print("[CASE 13] Role-Based Access Control (RBAC) & Security Bypassing")
    # 1) 일반 사원(STAFF) 권한으로 어드민 전용 URL 접속 차단 검증
    staff_client_req = TestClient(app)
    staff_client_req.cookies.set("access_token", f"Bearer {staff_token}")
    r_admin_dash = staff_client_req.get("/admin/dashboard", follow_redirects=False)
    assert r_admin_dash.status_code in (302, 403)
    
    # 2) 팀장(TEAM_LEAD)이 자신의 연차 신청 건에 대해 결재(Self-approval)를 시도하는 시나리오 차단 검증
    lead_token = auth.create_access_token({"sub": "u_lead"})
    lead_client = TestClient(app)
    lead_client.cookies.set("access_token", f"Bearer {lead_token}")
    
    db = SessionLocal()
    clear_user_leaves(db, "u_lead")
    db.commit()
    db.close()
    
    r_lead_apply = lead_client.post("/api/user/leave", data={
        "date_str": d1.strftime("%Y-%m-%d"), "start_time": "09:00", "end_time": "18:00"
    })
    assert r_lead_apply.status_code == 200
    
    db = SessionLocal()
    lead_leave = db.query(models.Leaves).filter(models.Leaves.user_id == "u_lead").first()
    assert lead_leave is not None
    assert lead_leave.status == "PENDING"
    db.close()
    
    r_self_approve = lead_client.post(f"/api/user/team-approve/{lead_leave.id}")
    assert r_self_approve.status_code in (400, 403)
    
    # 3) 팀장(TEAM_LEAD)이 다른 팀 소속 사원의 연차에 대해 결재를 시도하는 시나리오 차단 검증
    db = SessionLocal()
    lead_b = db.query(models.Users).filter(models.Users.user_id == "u_lead_b").first()
    if not lead_b:
        db.add(models.Users(
            user_id="u_lead_b", user_name="팀장B", role="TEAM_LEAD", team="Team-B",
            password=auth.get_password_hash("0000"), is_active=True
        ))
        db.commit()
    db.close()
    
    db = SessionLocal()
    clear_user_leaves(db, "u_staff")
    db.commit()
    db.close()
    
    r_staff_apply = staff_client.post("/api/user/leave", data={
        "date_str": d1.strftime("%Y-%m-%d"), "start_time": "09:00", "end_time": "18:00"
    })
    assert r_staff_apply.status_code == 200
    
    db = SessionLocal()
    staff_leave = db.query(models.Leaves).filter(models.Leaves.user_id == "u_staff").first()
    db.close()
    
    lead_b_token = auth.create_access_token({"sub": "u_lead_b"})
    lead_b_client = TestClient(app)
    lead_b_client.cookies.set("access_token", f"Bearer {lead_b_token}")
    
    r_other_approve = lead_b_client.post(f"/api/user/team-approve/{staff_leave.id}")
    assert r_other_approve.status_code == 403
    print("  -> PASS: RBAC check (Admin page block, self-approval block, other team block) verified.")

    # --- 시나리오 14: 정밀 시간 차감 정책 및 점심시간 제외 바운더리 검증 ---
    print("[CASE 14] Precise Time Policy Boundaries")
    # 1) 60분 단위 경계에 어긋나는 신청(예: 09:30 신청) 시 실패 검증
    r_invalid_time = staff_client.post("/api/user/leave", data={
        "date_str": d1.strftime("%Y-%m-%d"), "start_time": "09:30", "end_time": "11:30"
    })
    assert r_invalid_time.status_code == 400
    assert "시간 단위 경계" in r_invalid_time.json()["message"]
    
    # 2) 점심시간(12:00~13:00)을 걸쳐 연차를 신청한 경우(예: 11:00~14:00) 1시간 제외하고 2.0시간만 차감 검증
    db = SessionLocal()
    clear_user_leaves(db, "u_staff")
    db.commit()
    db.close()
    
    r_lunch_overlap = staff_client.post("/api/user/leave", data={
        "date_str": d1.strftime("%Y-%m-%d"), "start_time": "11:00", "end_time": "14:00"
    })
    assert r_lunch_overlap.status_code == 200
    
    db = SessionLocal()
    lunch_leave = db.query(models.Leaves).filter(models.Leaves.user_id == "u_staff").first()
    assert lunch_leave is not None
    assert lunch_leave.snapshot_deduction_hours == 2.0
    db.close()
    print("  -> PASS: Granularity boundaries and lunch exclusion verified.")

    # --- 시나리오 15: 퇴사자(비활성 사원) 로그인 원천 차단 검증 ---
    print("[CASE 15] Deactivated Employee Login Blocking")
    db = SessionLocal()
    staff_user_obj = db.query(models.Users).filter(models.Users.user_id == "u_staff").first()
    staff_user_obj.is_active = False
    db.commit()
    db.close()
    
    deactive_client = TestClient(app)
    r_deactive_login = deactive_client.post("/login", data={"user_id": "u_staff", "password": "new_staff_password"})
    assert r_deactive_login.status_code == 200
    assert "비활성" in r_deactive_login.text
    
    db = SessionLocal()
    staff_user_obj = db.query(models.Users).filter(models.Users.user_id == "u_staff").first()
    staff_user_obj.is_active = True
    db.commit()
    db.close()
    print("  -> PASS: Deactivated employee login successfully blocked.")

    # --- 시나리오 16: 수동 공휴일 지정에 따른 연차 신청 제한 검증 ---
    print("[CASE 16] Holiday Date Leave Application Blocking")
    test_holiday_date = date(2026, 10, 14)
    db = SessionLocal()
    db.query(models.Holidays).filter(models.Holidays.date == test_holiday_date).delete()
    db.commit()
    db.close()
    
    r_add_holiday = admin_client.post("/api/admin/holiday/create", data={
        "holiday_name": "테스트창립기념일",
        "holiday_date": "2026-10-14"
    })
    assert r_add_holiday.status_code in (200, 302)
    
    r_holiday_apply = staff_client.post("/api/user/leave", data={
        "date_str": "2026-10-14", "start_time": "09:00", "end_time": "18:00"
    })
    assert r_holiday_apply.status_code == 400
    assert "\uacf5\ud734\uc77c" in r_holiday_apply.json()["message"]
    
    db = SessionLocal()
    db.query(models.Holidays).filter(models.Holidays.date == test_holiday_date).delete()
    db.commit()
    db.close()
    print("  -> PASS: Leave application on registered holidays successfully blocked.")

    # --- 시나리오 17: 사원 강제 삭제 시 감사 로그 actor_id NULL 처리 및 정합성 검증 ---
    print("[CASE 17] User Hard-Delete with Audit Logs Integrity")
    db = SessionLocal()
    test_uid = "u_temp_delete"
    
    # 1. 이전 잔재가 있다면 청소
    db.query(models.AuditLogs).filter(models.AuditLogs.actor_id == test_uid).delete()
    db.query(models.Leaves).filter(models.Leaves.user_id == test_uid).delete()
    db.query(models.UserYearlyLeaveAllocations).filter(models.UserYearlyLeaveAllocations.user_id == test_uid).delete()
    db.query(models.Users).filter(models.Users.user_id == test_uid).delete()
    db.commit()
    
    # 2. 신규 사용자 및 연관 데이터 생성
    db.add(models.Users(
        user_id=test_uid, user_name="임시사원", role="STAFF",
        password=auth.get_password_hash("0000"), is_active=True
    ))
    db.commit()
    
    # 3. 감사 로그 생성 (이 사용자가 actor가 됨)
    db.add(models.AuditLogs(
        actor_id=test_uid, action="TEST_ACTION_BY_USER",
        target_info="Test Target", old_data="old", new_data="new"
    ))
    # 4. 연차 할당 및 신청 데이터 생성
    db.add(models.UserYearlyLeaveAllocations(user_id=test_uid, year=2026, allocated_hours=120))
    db.add(models.Leaves(
        user_id=test_uid, date=date(2026, 11, 20), snapshot_slot_label="09:00 - 18:00",
        snapshot_start_min=540, snapshot_end_min=1080, snapshot_deduction_hours=8.0,
        status="APPROVED", year=2026
    ))
    db.commit()
    
    # 생성된 감사 로그 ID 확보
    audit_row = db.query(models.AuditLogs).filter(models.AuditLogs.actor_id == test_uid).first()
    assert audit_row is not None
    audit_id = audit_row.id
    db.close()
    
    # 5. 관리자 권한으로 사원 강제 삭제 API 호출
    r_delete = admin_client.post("/api/admin/user/hard-delete", data={"target_user_id": test_uid})
    assert r_delete.status_code == 200
    
    # 6. DB 정합성 최종 검증
    db = SessionLocal()
    # 사원 레코드 삭제 확인
    assert db.query(models.Users).filter(models.Users.user_id == test_uid).first() is None
    # 연차 및 할당 삭제 확인
    assert db.query(models.Leaves).filter(models.Leaves.user_id == test_uid).all() == []
    assert db.query(models.UserYearlyLeaveAllocations).filter(models.UserYearlyLeaveAllocations.user_id == test_uid).all() == []
    # 감사 로그는 남아있되, actor_id만 NULL로 정상 업데이트 되었는지 검증
    audit_after = db.query(models.AuditLogs).filter(models.AuditLogs.id == audit_id).first()
    assert audit_after is not None
    assert audit_after.actor_id is None
    
    # 청소
    db.query(models.AuditLogs).filter(models.AuditLogs.id == audit_id).delete()
    db.commit()
    db.close()
    print("  -> PASS: User hard-delete with audit logs integrity verified successfully.")

    print("\n[COMPLETE] All key features verified successfully.")
    db = SessionLocal()
    db.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[FAILURE] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
