from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    original_data_dir = os.environ.get("SHIM_DATA_DIR")
    original_secret = os.environ.get("SHIM_SECRET_KEY")
    with tempfile.TemporaryDirectory(prefix="shim_mobile_ui_") as temp_dir:
        os.environ["SHIM_DATA_DIR"] = temp_dir
        os.environ.pop("SHIM_SECRET_KEY", None)
        from fastapi.testclient import TestClient
        from src.app import auth, database, models
        from src.app.main import app, startup_event
        from src.app.services.leave_policy import get_system_settings

        database.Base.metadata.create_all(bind=database.engine)
        startup_event()
        db = database.SessionLocal()
        try:
            password_hash = auth.get_password_hash("0000")
            users = [
                models.Users(user_id="mobile_staff", user_name="모바일 사용자", company="SHIM", team="개발팀", password=password_hash, role="STAFF", total_leave_hours=120),
                models.Users(user_id="mobile_lead", user_name="팀 리더", company="SHIM", team="개발팀", password=password_hash, role="TEAM_LEAD", total_leave_hours=120),
                models.Users(user_id="other_staff", user_name="다른 팀 사용자", company="SHIM", team="운영팀", password=password_hash, role="STAFF", total_leave_hours=120),
                models.Users(user_id="mobile_pm", user_name="프로젝트 관리자", company="SHIM", team="PM", password=password_hash, role="PM", total_leave_hours=120),
                models.Users(user_id="mobile_admin", user_name="시스템 관리자", company="SHIM", team="관리", password=password_hash, role="ADMIN", total_leave_hours=120),
            ]
            db.add_all(users)
            db.flush()
            for user_id, day, reason in (
                ("mobile_staff", 29, "<긴 사유>&" + "가" * 200),
                ("other_staff", 28, "다른 팀 일정"),
                ("mobile_admin", 27, "관리자 일정"),
            ):
                db.add(models.Leaves(
                    user_id=user_id, date=date(2024, 2, day), snapshot_slot_label="09:00~18:00",
                    snapshot_start_min=540, snapshot_end_min=1080, snapshot_deduction_hours=8.0,
                    status="APPROVED", is_deductive=True, reason=reason, year=2024,
                ))
            db.commit()

            def client_for(user_id: str) -> TestClient:
                client = TestClient(app)
                token = auth.create_access_token({"sub": user_id, "token_version": 0})
                client.cookies.set("access_token", f"Bearer {token}")
                return client

            anonymous = TestClient(app)
            for path in (
                "/user/calendar/desktop-partial?year=2024",
                "/user/team-calendar/desktop-partial?year=2024&month=2",
                "/api/user/calendar-month?year=2024&month=2",
                "/api/user/team-calendar?year=2024&month=2",
            ):
                assert anonymous.get(path, follow_redirects=False).status_code in (302, 401, 403)

            staff = client_for("mobile_staff")
            team_shell = staff.get("/user/team-calendar?year=2024&month=2")
            team_partial = staff.get("/user/team-calendar/desktop-partial?year=2024&month=2")
            assert team_shell.status_code == team_partial.status_code == 200
            assert 'id="team-desktop-container-g"' in team_shell.text
            assert "<table" not in team_shell.text
            assert "<table" in team_partial.text and "<!DOCTYPE html>" not in team_partial.text

            team_payload = staff.get("/api/user/team-calendar?year=2024&month=2").json()
            assert team_payload["days_in_month"] == 29
            visible_names = {item["user_name"] for items in team_payload["days"].values() for item in items}
            assert "모바일 사용자" in visible_names
            assert "다른 팀 사용자" not in visible_names
            assert "시스템 관리자" not in visible_names

            for path in (
                "/api/user/team-calendar?year=2024&month=0",
                "/api/user/team-calendar?year=2024&month=13",
                "/api/user/calendar-month?year=2024&month=0",
                "/api/user/calendar-month?year=2024&month=13",
            ):
                assert staff.get(path).status_code == 422

            assert staff.get("/api/user/team-calendar?year=2023&month=12").json()["days_in_month"] == 31
            assert staff.get("/api/user/team-calendar?year=2024&month=1").json()["days_in_month"] == 31

            calendar_shell = staff.get("/user/calendar?year=2024&month=2")
            calendar_partial = staff.get("/user/calendar/desktop-partial?year=2024&month=2")
            assert calendar_shell.status_code == calendar_partial.status_code == 200
            assert 'id="mobile-calendar-grid-g"' in calendar_shell.text
            assert 'id="calendar-desktop-container-g"' in calendar_shell.text
            assert 'id="calendar-desktop-container-g" class="hidden lg:block"' in calendar_shell.text
            assert "container.className = 'hidden lg:block';" in calendar_shell.text
            assert 'id="shim-prompt-btn" class="inline-flex min-h-11' in calendar_shell.text
            assert 'id="shim-prompt-cancel-btn" class="inline-flex min-h-11' in calendar_shell.text
            assert 'id="shim-prompt-cancel-btn" class="mt-3' not in calendar_shell.text
            assert "selectedYearVal" not in calendar_shell.text
            assert "label.textContent = `2024년 ${m}월`" in calendar_shell.text
            assert 'id="month-card-1"' not in calendar_shell.text
            assert 'id="month-card-1"' in calendar_partial.text

            leap_payload = staff.get("/api/user/calendar-month?year=2024&month=2").json()
            normal_payload = staff.get("/api/user/calendar-month?year=2025&month=2").json()
            assert leap_payload["days_in_month"] == 29
            assert normal_payload["days_in_month"] == 28
            assert leap_payload["days"]["29"][0]["reason"].startswith("<긴 사유>&")
            assert "<긴 사유>&" not in calendar_shell.text

            history = staff.get("/user/history?year=2024")
            assert history.status_code == 200
            assert "2024년 나의 신청 내역" in history.text
            assert 'id="mobile-history-year"' in history.text
            assert 'id="shim-account-menu-btn"' in history.text
            assert "hidden lg:flex" in history.text
            assert "block lg:hidden" in history.text
            assert "hidden md:flex" not in history.text
            assert "block md:hidden" not in history.text

            setting = db.query(models.SystemSettings).first()
            setting.is_approval_required = True
            db.commit()
            get_system_settings(db, force_reload=True)

            lead = client_for("mobile_lead")
            approvals = lead.get("/user/approvals")
            assert approvals.status_code == 200
            assert 'href="/user/approvals"' in approvals.text
            assert "hidden lg:flex" in approvals.text
            assert "block lg:hidden" in approvals.text
            assert "hidden md:flex" not in approvals.text
            assert "block md:hidden" not in approvals.text
            for mobile_page in (team_shell, history, approvals):
                assert 'aria-label="캘린더 홈으로"' in mobile_page.text
                assert 'class="flex min-h-11 w-fit items-center gap-2 rounded-lg' in mobile_page.text
                assert '<svg aria-hidden="true" viewBox="0 0 20 20"' in mobile_page.text


            lead_calendar = lead.get("/user/calendar?year=2024&month=2")
            assert "✅ 결재 관리" in lead_calendar.text
            assert "신청 승인·반려" in lead_calendar.text
            assert 'href="/user/approvals" class="quick-card flex min-h-[4.75rem]' in lead_calendar.text
            assert 'href="/user/history" class="quick-card flex min-h-[4.75rem]' in lead_calendar.text
            assert "bg-gradient-to-br from-dense" not in lead_calendar.text
            assert lead_calendar.text.count("quick-card flex min-h-[4.75rem]") == 4

            pm_payload = client_for("mobile_pm").get("/api/user/team-calendar?year=2024&month=2").json()
            pm_names = {item["user_name"] for items in pm_payload["days"].values() for item in items}
            assert "다른 팀 사용자" in pm_names
            assert "시스템 관리자" not in pm_names

            lead_payload = client_for("mobile_lead").get("/api/user/team-calendar?year=2024&month=2").json()
            lead_names = {item["user_name"] for items in lead_payload["days"].values() for item in items}
            assert "모바일 사용자" in lead_names
            assert "다른 팀 사용자" not in lead_names

            admin = client_for("mobile_admin")
            admin_shell = admin.get("/user/team-calendar?year=2024&month=2")
            assert admin_shell.status_code == 200
            assert 'id="mobile-schedule-view-g"' in admin_shell.text
            assert "시스템 관리자" not in {
                item["user_name"]
                for items in admin.get("/api/user/team-calendar?year=2024&month=2").json()["days"].values()
                for item in items
            }

            print(
                "[PASS] MOB-001~006 mobile UI checks completed "
                f"(team shell={len(team_shell.content)}B/{team_shell.text.count('<td')}td, "
                f"team partial={len(team_partial.content)}B/{team_partial.text.count('<td')}td, "
                f"calendar shell={len(calendar_shell.content)}B/{calendar_shell.text.count('<td')}td, "
                f"calendar partial={len(calendar_partial.content)}B/{calendar_partial.text.count('<td')}td)."
            )
            return 0
        finally:
            db.close()
            database.engine.dispose()
            if original_secret is None:
                os.environ.pop("SHIM_SECRET_KEY", None)
            else:
                os.environ["SHIM_SECRET_KEY"] = original_secret
            if original_data_dir is None:
                os.environ.pop("SHIM_DATA_DIR", None)
            else:
                os.environ["SHIM_DATA_DIR"] = original_data_dir


if __name__ == "__main__":
    raise SystemExit(main())
