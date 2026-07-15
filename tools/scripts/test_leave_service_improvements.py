from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _restore_env(name: str, original: str | None) -> None:
    if original is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = original


def _expect_validation_error(callback) -> None:
    from src.app.services.leave_policy import LeaveInputValidationError

    try:
        callback()
    except LeaveInputValidationError:
        return
    raise AssertionError("LeaveInputValidationError가 발생해야 합니다.")


def _weekdays(start: date, count: int) -> list[date]:
    result = []
    current = start
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return result


def main() -> int:
    original_data_dir = os.environ.get("SHIM_DATA_DIR")
    original_secret = os.environ.get("SHIM_SECRET_KEY")

    with tempfile.TemporaryDirectory(prefix="shim_leave_test_") as temp_dir:
        os.environ["SHIM_DATA_DIR"] = temp_dir
        os.environ.pop("SHIM_SECRET_KEY", None)

        from src.app import auth, database, models
        from src.app.services import leave_policy, leave_service

        database.Base.metadata.create_all(bind=database.engine)
        db = database.SessionLocal()
        try:
            setting = models.SystemSettings(
                is_approval_required=False,
                time_granularity_minutes=60,
                work_start_minute=9 * 60,
                work_end_minute=18 * 60,
            )
            password_hash = auth.get_password_hash("0000")
            users = [
                models.Users(
                    user_id=user_id,
                    user_name=user_id,
                    password=password_hash,
                    role="PM",
                    total_leave_hours=120,
                )
                for user_id in ("leave_basic", "leave_null_lunch", "leave_boundary", "leave_race")
            ]
            db.add(setting)
            db.add_all(users)
            db.commit()
            db.refresh(setting)
            assert setting.lunch_start_minute == 12 * 60
            assert setting.lunch_end_minute == 13 * 60
            leave_policy.get_system_settings(db, force_reload=True)

            basic_user = users[0]
            message = leave_service.validate_and_apply_leave(
                db,
                basic_user,
                "2030-02-01,2030-02-01",
                "09:00",
                "10:00",
                True,
                "",
            )
            assert message == "신청 및 자동 승인되었습니다."
            same_day = db.query(models.Leaves).filter(
                models.Leaves.user_id == basic_user.user_id,
                models.Leaves.date == date(2030, 2, 1),
            ).all()
            assert len(same_day) == 1

            leave_service.validate_and_apply_leave(
                db, basic_user, "2030-02-01", "15:00", "16:00", True, ""
            )
            assert db.query(models.Leaves).filter(
                models.Leaves.user_id == basic_user.user_id,
                models.Leaves.date == date(2030, 2, 1),
            ).count() == 2

            for start_time, end_time in (("14:00", ""), ("", "15:00"), ("  ", "15:00")):
                _expect_validation_error(
                    lambda start_time=start_time, end_time=end_time: leave_service.validate_and_apply_leave(
                        db,
                        basic_user,
                        "2030-02-04",
                        start_time,
                        end_time,
                        True,
                        "",
                    )
                )

            leave_service.validate_and_apply_leave(
                db, basic_user, "2030-02-04", "", "", True, ""
            )
            full_day = db.query(models.Leaves).filter(
                models.Leaves.user_id == basic_user.user_id,
                models.Leaves.date == date(2030, 2, 4),
            ).one()
            assert full_day.snapshot_deduction_hours == 8.0

            setting.lunch_start_minute = None
            setting.lunch_end_minute = None
            db.commit()
            leave_policy.get_system_settings(db, force_reload=True)
            null_lunch_user = users[1]
            leave_service.validate_and_apply_leave(
                db, null_lunch_user, "2030-02-05", "", "", True, ""
            )
            null_lunch_leave = db.query(models.Leaves).filter(
                models.Leaves.user_id == null_lunch_user.user_id,
            ).one()
            assert null_lunch_leave.snapshot_deduction_hours == 9.0

            setting.lunch_start_minute = 12 * 60
            setting.lunch_end_minute = 13 * 60
            db.commit()
            leave_policy.get_system_settings(db, force_reload=True)
            boundary_user = users[2]
            fifteen_days = _weekdays(date(2030, 3, 1), 15)
            leave_service.validate_and_apply_leave(
                db,
                boundary_user,
                ",".join(day.isoformat() for day in fifteen_days),
                "",
                "",
                True,
                "",
            )
            assert db.query(models.Leaves).filter(
                models.Leaves.user_id == boundary_user.user_id,
            ).count() == 15
            next_day = _weekdays(fifteen_days[-1] + timedelta(days=1), 1)[0]
            _expect_validation_error(
                lambda: leave_service.validate_and_apply_leave(
                    db, boundary_user, next_day.isoformat(), "", "", True, ""
                )
            )

            db.commit()
            race_barrier = Barrier(2)

            def submit_race_request() -> str:
                session = database.SessionLocal()
                try:
                    race_user = session.query(models.Users).filter(
                        models.Users.user_id == "leave_race"
                    ).one()
                    race_barrier.wait(timeout=10)
                    try:
                        leave_service.validate_and_apply_leave(
                            session, race_user, "2030-04-01", "09:00", "10:00", True, ""
                        )
                        return "success"
                    except leave_policy.LeaveInputValidationError:
                        return "rejected"
                finally:
                    session.close()

            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="leave-race") as executor:
                race_results = list(executor.map(lambda _: submit_race_request(), range(2)))

            assert sorted(race_results) == ["rejected", "success"]
            assert db.query(models.Leaves).filter(
                models.Leaves.user_id == "leave_race",
                models.Leaves.date == date(2030, 4, 1),
            ).count() == 1

            print("[PASS] LEAVE-001/002/003 regression checks completed.")
            return 0
        finally:
            db.close()
            database.engine.dispose()
            _restore_env("SHIM_SECRET_KEY", original_secret)
            _restore_env("SHIM_DATA_DIR", original_data_dir)


if __name__ == "__main__":
    raise SystemExit(main())
