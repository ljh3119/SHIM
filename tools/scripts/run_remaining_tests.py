from datetime import date, timedelta
import os
from pathlib import Path
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TEST_DATA_DIR = Path(
    os.environ.setdefault("SHIM_DATA_DIR", tempfile.mkdtemp(prefix="shim_remaining_tests_"))
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


def clear_user_day_leaves(db, user_id, target_date):
    db.query(models.Leaves).filter(
        models.Leaves.user_id == user_id,
        models.Leaves.date == target_date,
    ).delete(synchronize_session=False)


def main():
    print("test_data_dir", TEST_DATA_DIR)
    startup_event()
    client = TestClient(app)
    db = SessionLocal()

    user = db.query(models.Users).filter(models.Users.user_id == "u_test").first()
    if not user:
        user = models.Users(
            user_id="u_test",
            user_name="테스트사용자",
            company="QA",
            team="AUTOTEST",
            password=auth.get_password_hash("0000"),
            total_leave_hours=120,
            is_active=True,
            is_admin=False,
        )
        db.add(user)
        db.commit()

    base = date.today() + timedelta(days=1)
    d1 = next_weekday(base)
    d2 = next_weekday(d1 + timedelta(days=1))

    holiday_dates = {
        h.date
        for h in db.query(models.Holidays)
        .filter(models.Holidays.date >= d1, models.Holidays.date <= d2 + timedelta(days=14))
        .all()
    }
    while d1 in holiday_dates or d1.weekday() >= 5:
        d1 += timedelta(days=1)
    while d2 in holiday_dates or d2.weekday() >= 5 or d2 == d1:
        d2 += timedelta(days=1)

    clear_user_day_leaves(db, "u_test", d1)
    clear_user_day_leaves(db, "u_test", d2)
    db.commit()

    user_token = auth.create_access_token({"sub": "u_test"})
    client.cookies.set("access_token", f"Bearer {user_token}")

    admin_token = auth.create_access_token({"sub": "admin"})
    admin_client = TestClient(app)
    admin_client.cookies.set("access_token", f"Bearer {admin_token}")

    r = admin_client.post("/admin/settings/approval", data={"is_approval_required": "false"})
    assert r.status_code == 200, f"승인 OFF 설정 실패: {r.text}"
    r = admin_client.post(
        "/admin/settings/time-policy",
        data={
            "time_granularity_minutes": "60",
            "work_start_minute": str(9 * 60),
            "work_end_minute": str(18 * 60),
            "lunch_start_minute": "-1",
            "lunch_end_minute": "-1",
        },
    )
    assert r.status_code == 200, f"시간 정책(60분) 설정 실패: {r.text}"

    r = client.post(
        "/user/leave",
        data={"date_str": d1.strftime("%Y-%m-%d"), "start_time": "14:00", "end_time": "18:00"},
    )
    assert r.status_code == 200, f"신청(OFF) 실패: {r.text}"

    leaves_off = db.query(models.Leaves).filter(models.Leaves.user_id == "u_test", models.Leaves.date == d1).all()
    assert len(leaves_off) == 1, f"시간입력 1건 저장 기대(OFF), 생성건수={len(leaves_off)}"
    assert all(l.status == "APPROVED" for l in leaves_off), "OFF 상태 기대값 APPROVED 불일치"
    assert sum(float(l.snapshot_deduction_hours) for l in leaves_off) == 4.0, "총 차감시간 4.0 아님"

    r = admin_client.post("/admin/settings/approval", data={"is_approval_required": "true"})
    assert r.status_code == 200, f"승인 ON 설정 실패: {r.text}"

    r = client.post(
        "/user/leave",
        data={"date_str": d2.strftime("%Y-%m-%d"), "start_time": "14:00", "end_time": "18:00"},
    )
    assert r.status_code == 200, f"신청(ON) 실패: {r.text}"

    leaves_on = db.query(models.Leaves).filter(models.Leaves.user_id == "u_test", models.Leaves.date == d2).all()
    assert len(leaves_on) == 1, f"시간입력 1건 저장 기대(ON), 생성건수={len(leaves_on)}"
    assert all(l.status == "PENDING" for l in leaves_on), "ON 상태 기대값 PENDING 불일치"

    leave_id = leaves_on[0].id
    r = admin_client.post("/admin/leave/update-status", data={"leave_id": str(leave_id), "status_value": "REJECTED"})
    assert r.status_code == 400, "반려 사유 없는 REJECTED 전이가 차단되지 않았습니다."
    db.refresh(leaves_on[0])
    assert leaves_on[0].status == "PENDING", "반려 사유 누락 실패 후 상태가 변경되었습니다."

    r = admin_client.post(
        "/admin/leave/update-status",
        data={"leave_id": str(leave_id), "status_value": "REJECTED", "rejection_reason": "   "},
    )
    assert r.status_code == 400, "공백 반려 사유가 차단되지 않았습니다."

    r = admin_client.post(
        "/admin/leave/update-status",
        data={"leave_id": str(leave_id), "status_value": "REJECTED", "rejection_reason": "가" * 501},
    )
    assert r.status_code == 400, "500자 초과 반려 사유가 차단되지 않았습니다."

    reject_reason = "테스트 반려 사유"
    r = admin_client.post(
        "/admin/leave/update-status",
        data={"leave_id": str(leave_id), "status_value": "REJECTED", "rejection_reason": reject_reason},
    )
    assert r.status_code == 200, f"반려 사유 포함 상태 변경 실패: {r.text}"
    db.refresh(leaves_on[0])
    assert leaves_on[0].status == "REJECTED", f"상태 변경 반영 실패, 실제={leaves_on[0].status}"
    assert leaves_on[0].rejection_reason == reject_reason, "반려 사유 저장 실패"

    r = admin_client.post("/admin/leave/update-status", data={"leave_id": str(leave_id), "status_value": "APPROVED"})
    assert r.status_code == 400, "REJECTED -> APPROVED 차단 규칙이 동작하지 않았습니다."

    d3 = next_weekday(d2 + timedelta(days=1))
    clear_user_day_leaves(db, "u_test", d3)
    db.commit()
    r = client.post(
        "/user/leave",
        data={"date_str": d3.strftime("%Y-%m-%d"), "start_time": "15:15", "end_time": "16:15"},
    )
    assert r.status_code == 400, "임의 분 입력이 차단되지 않았습니다."

    d4 = next_weekday(d3 + timedelta(days=1))
    clear_user_day_leaves(db, "u_test", d4)
    db.commit()
    r = client.post(
        "/user/leave",
        data={"date_str": d4.strftime("%Y-%m-%d"), "start_time": "13:00", "end_time": "15:00"},
    )
    assert r.status_code == 200, f"시작/종료 입력 신청 실패: {r.text}"
    leaves_range = db.query(models.Leaves).filter(models.Leaves.user_id == "u_test", models.Leaves.date == d4).all()
    assert len(leaves_range) == 1, f"시작/종료 입력은 1건 스냅샷 저장 기대, 실제={len(leaves_range)}"
    assert float(leaves_range[0].snapshot_deduction_hours) == 2.0, "시작/종료 입력 차감 시간이 기대값(2h)과 다릅니다."

    pending_count = db.query(models.Leaves).filter(models.Leaves.status == "PENDING").count()
    print("PASS")
    print("date_off", d1.isoformat(), "count", len(leaves_off), "total_deduction", sum(float(l.snapshot_deduction_hours) for l in leaves_off))
    print("date_on", d2.isoformat(), "count", len(leaves_on), "status_after_one", leaves_on[0].status)
    print("pending_count_now", pending_count)
    print("date_range_ok", d4.isoformat(), "deduction", float(leaves_range[0].snapshot_deduction_hours))

    db.close()


if __name__ == "__main__":
    main()
