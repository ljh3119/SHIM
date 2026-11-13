import os
import sys
import tempfile
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    temp_dir = tempfile.TemporaryDirectory(prefix="shim_holiday_test_")
    orig_data_dir = os.environ.get("SHIM_DATA_DIR")
    orig_secret = os.environ.get("SHIM_SECRET_KEY")
    os.environ["SHIM_DATA_DIR"] = temp_dir.name
    os.environ["SHIM_SECRET_KEY"] = "test_secret_key_32_bytes_long_12345"

    try:
        from src.app import database, models
        from src.app.main import seed_korean_holidays, _compact_kr_holiday_name

        database.Base.metadata.create_all(bind=database.engine)
        with database.SessionLocal() as db:
            admin_user = models.Users(
                user_id="admin_tester",
                password="test_password_hash",
                user_name="관리자테스터",
                role="ADMIN",
                is_active=True,
            )
            db.add(admin_user)
            db.commit()

            # 1. Verify fresh DB holiday seeding for 2026 and 2027
            seed_korean_holidays(db, actor_id="admin_tester", start_year=2026, end_year=2027)
            db.commit()

            # Check 2026-12-25 Christmas
            h_2026_xmas = db.query(models.Holidays).filter(models.Holidays.date == date(2026, 12, 25)).first()
            assert h_2026_xmas is not None, "2026-12-25 holiday must exist"
            assert h_2026_xmas.name == "크리스마스", f"Expected '크리스마스', got '{h_2026_xmas.name}'"

            # Check 2027-12-25 Christmas
            h_2027_xmas = db.query(models.Holidays).filter(models.Holidays.date == date(2027, 12, 25)).first()
            assert h_2027_xmas is not None, "2027-12-25 holiday must exist"
            assert h_2027_xmas.name == "크리스마스", f"Expected '크리스마스', got '{h_2027_xmas.name}'"

            # Check 2027-12-27 Christmas substitute holiday
            h_2027_sub = db.query(models.Holidays).filter(models.Holidays.date == date(2027, 12, 27)).first()
            assert h_2027_sub is not None, "2027-12-27 substitute holiday must exist"
            assert h_2027_sub.name == "크리스마스 대체 휴일", f"Expected '크리스마스 대체 휴일', got '{h_2027_sub.name}'"

            # Check Labor Day and Constitution Day
            h_labor = db.query(models.Holidays).filter(models.Holidays.date == date(2026, 5, 1)).first()
            assert h_labor is not None and h_labor.name == "노동절"

            h_const = db.query(models.Holidays).filter(models.Holidays.date == date(2026, 7, 17)).first()
            assert h_const is not None and h_const.name == "제헌절"

            # 2. Verify admin editing preservation and seed re-run idempotency
            # Simulate admin editing the holiday name
            h_2026_xmas.name = "성탄절(사용자수정)"
            db.commit()

            # Re-run seeding for the same years
            seed_korean_holidays(db, actor_id="admin_tester", start_year=2026, end_year=2027)
            db.commit()

            # Admin edit must be preserved because SEED_KR_HOLIDAYS_2026 audit log prevents re-seeding
            h_rechecked = db.query(models.Holidays).filter(models.Holidays.date == date(2026, 12, 25)).first()
            assert h_rechecked.name == "성탄절(사용자수정)", f"Admin edit overwritten: '{h_rechecked.name}'"

            # 3. Unit test mapping function directly
            assert _compact_kr_holiday_name("기독탄신일") == "크리스마스"
            assert _compact_kr_holiday_name("기독탄신일 대체 휴일") == "크리스마스 대체 휴일"
            assert _compact_kr_holiday_name("설날 연휴") == "설 연휴"
            assert _compact_kr_holiday_name("추석 연휴") == "추석 연휴"
            assert _compact_kr_holiday_name("어린이날") == "어린이날"

            print("[PASS] test_holiday_names passed successfully.")
            return 0
    finally:
        database.engine.dispose()
        temp_dir.cleanup()
        if orig_data_dir is not None:
            os.environ["SHIM_DATA_DIR"] = orig_data_dir
        else:
            os.environ.pop("SHIM_DATA_DIR", None)
        if orig_secret is not None:
            os.environ["SHIM_SECRET_KEY"] = orig_secret
        else:
            os.environ.pop("SHIM_SECRET_KEY", None)


if __name__ == "__main__":
    sys.exit(main())
