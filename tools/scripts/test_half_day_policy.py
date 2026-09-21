import os
import sys
import tempfile
from pathlib import Path

# Set up project path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.app.services.leave_policy import (
    ALLOWED_TIME_GRANULARITIES,
    HALF_DAY_MINUTES,
    resolve_half_day_slots,
    build_snapshot_from_timerange,
    LeaveInputValidationError,
)


def test_allowed_granularities():
    assert 240 in ALLOWED_TIME_GRANULARITIES, "240 should be in ALLOWED_TIME_GRANULARITIES"
    assert HALF_DAY_MINUTES == 240


def test_resolve_half_day_slots_default_work_hours():
    # 09:00 (540) ~ 18:00 (1080), Lunch: 12:00 (720) ~ 13:00 (780)
    slots = resolve_half_day_slots(
        work_start_minute=540,
        work_end_minute=1080,
        lunch_start_minute=720,
        lunch_end_minute=780,
    )
    assert slots["morning"]["start_time"] == "09:00"
    assert slots["morning"]["end_time"] == "14:00"
    assert slots["morning"]["start_min"] == 540
    assert slots["morning"]["end_min"] == 840

    assert slots["afternoon"]["start_time"] == "14:00"
    assert slots["afternoon"]["end_time"] == "18:00"
    assert slots["afternoon"]["start_min"] == 840
    assert slots["afternoon"]["end_min"] == 1080


def test_resolve_half_day_slots_without_lunch():
    # 09:00 (540) ~ 18:00 (1080), No lunch
    slots = resolve_half_day_slots(
        work_start_minute=540,
        work_end_minute=1080,
        lunch_start_minute=None,
        lunch_end_minute=None,
    )
    assert slots["morning"]["start_time"] == "09:00"
    assert slots["morning"]["end_time"] == "13:00"

    assert slots["afternoon"]["start_time"] == "14:00"
    assert slots["afternoon"]["end_time"] == "18:00"


def test_half_day_snapshot_deduction():
    # Morning half: 09:00 ~ 14:00 (Lunch 12:00~13:00 excluded -> 4.0h)
    snapshot_m = build_snapshot_from_timerange(
        start_time="09:00",
        end_time="14:00",
        granularity_minutes=240,
        lunch_start_minute=720,
        lunch_end_minute=780,
        work_start_minute=540,
        work_end_minute=1080,
    )
    assert snapshot_m.slot_label == "09:00~14:00"
    assert snapshot_m.deduction_hours == 4.0
    assert snapshot_m.start_min == 540
    assert snapshot_m.end_min == 840

    # Afternoon half: 14:00 ~ 18:00 (No lunch overlap -> 4.0h)
    snapshot_a = build_snapshot_from_timerange(
        start_time="14:00",
        end_time="18:00",
        granularity_minutes=240,
        lunch_start_minute=720,
        lunch_end_minute=780,
        work_start_minute=540,
        work_end_minute=1080,
    )
    assert snapshot_a.slot_label == "14:00~18:00"
    assert snapshot_a.deduction_hours == 4.0

    # Full day: 09:00 ~ 18:00 (Lunch 12:00~13:00 excluded -> 8.0h)
    snapshot_full = build_snapshot_from_timerange(
        start_time="09:00",
        end_time="18:00",
        granularity_minutes=240,
        lunch_start_minute=720,
        lunch_end_minute=780,
        work_start_minute=540,
        work_end_minute=1080,
    )
    assert snapshot_full.slot_label == "09:00~18:00"
    assert snapshot_full.deduction_hours == 8.0


def test_half_day_rejects_arbitrary_ranges():
    # In 240 policy, arbitrary 1 hour should be rejected
    try:
        build_snapshot_from_timerange(
            start_time="09:00",
            end_time="10:00",
            granularity_minutes=240,
            lunch_start_minute=720,
            lunch_end_minute=780,
            work_start_minute=540,
            work_end_minute=1080,
        )
        assert False, "Should raise LeaveInputValidationError"
    except LeaveInputValidationError as e:
        assert "반일(240분) 단위 정책에서는" in str(e)

    # Arbitrary non-standard 4 hours (e.g., 10:00 ~ 15:00) should be rejected in 240 policy
    try:
        build_snapshot_from_timerange(
            start_time="10:00",
            end_time="15:00",
            granularity_minutes=240,
            lunch_start_minute=720,
            lunch_end_minute=780,
            work_start_minute=540,
            work_end_minute=1080,
        )
        assert False, "Should raise LeaveInputValidationError"
    except LeaveInputValidationError as e:
        assert "반일(240분) 단위 정책에서는" in str(e)


def test_half_day_preset_allowed_in_other_granularities():
    # 09:00 ~ 14:00 (morning half) should be accepted in 30, 60, and 120 policies as standard preset
    for g in (30, 60, 120):
        snap = build_snapshot_from_timerange(
            start_time="09:00",
            end_time="14:00",
            granularity_minutes=g,
            lunch_start_minute=720,
            lunch_end_minute=780,
            work_start_minute=540,
            work_end_minute=1080,
        )
        assert snap.deduction_hours == 4.0

        snap_a = build_snapshot_from_timerange(
            start_time="14:00",
            end_time="18:00",
            granularity_minutes=g,
            lunch_start_minute=720,
            lunch_end_minute=780,
            work_start_minute=540,
            work_end_minute=1080,
        )
        assert snap_a.deduction_hours == 4.0


def test_admin_settings_time_policy_endpoint():
    with tempfile.TemporaryDirectory(prefix="shim_policy_test_") as temp_dir:
        os.environ["SHIM_DATA_DIR"] = temp_dir
        os.environ.pop("SHIM_SECRET_KEY", None)

        from fastapi.testclient import TestClient
        from src.app import auth, database, models
        from src.app.main import app

        database.Base.metadata.create_all(bind=database.engine)
        db = database.SessionLocal()
        try:
            # Seed admin user
            admin = models.Users(
                user_id="admin_test",
                user_name="Admin Test",
                password=auth.get_password_hash("testpass123"),
                role="ADMIN",
                is_active=True,
            )
            db.add(admin)
            setting = models.SystemSettings(
                time_granularity_minutes=60,
                work_start_minute=540,
                work_end_minute=1080,
                lunch_start_minute=720,
                lunch_end_minute=780,
            )
            db.add(setting)
            db.commit()

            token = auth.create_access_token(data={"sub": "admin_test", "role": "ADMIN", "token_version": 0})
        finally:
            db.close()

        client = TestClient(app)
        client.cookies.set("access_token", token)

        # 1) Set granularity to 240 -> should succeed
        res = client.post(
            "/api/admin/settings/time-policy",
            data={
                "time_granularity_minutes": "240",
                "work_start_minute": "540",
                "work_end_minute": "1080",
                "lunch_start_minute": "720",
                "lunch_end_minute": "780",
            },
        )
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

        # Verify DB updated
        db = database.SessionLocal()
        try:
            saved_setting = db.query(models.SystemSettings).first()
            assert saved_setting.time_granularity_minutes == 240

            # Verify audit log recorded
            audit = db.query(models.AuditLogs).order_by(models.AuditLogs.id.desc()).first()
            assert "granularity=240" in audit.new_data
        finally:
            db.close()

        # 2) Set granularity to invalid 999 -> should fail with 400
        res_invalid = client.post(
            "/api/admin/settings/time-policy",
            data={
                "time_granularity_minutes": "999",
                "work_start_minute": "540",
                "work_end_minute": "1080",
                "lunch_start_minute": "720",
                "lunch_end_minute": "780",
            },
        )
        assert res_invalid.status_code == 400, f"Expected 400, got {res_invalid.status_code}"
        assert "30/60/120/240" in res_invalid.json()["message"]


if __name__ == "__main__":
    test_allowed_granularities()
    test_resolve_half_day_slots_default_work_hours()
    test_resolve_half_day_slots_without_lunch()
    test_half_day_snapshot_deduction()
    test_half_day_rejects_arbitrary_ranges()
    test_half_day_preset_allowed_in_other_granularities()
    test_admin_settings_time_policy_endpoint()
    print("[PASS] test_half_day_policy passed successfully.")
