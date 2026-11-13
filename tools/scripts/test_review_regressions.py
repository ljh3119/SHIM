"""입력 처리, 동시 전이, 배정량, 시간 정책, 백업 호환성 회귀 검사."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.buttons, self.scripts = [], []
        self.script = None

    def handle_starttag(self, tag, attrs):
        if tag == "button":
            self.buttons.append(dict(attrs))
        if tag == "script":
            self.script = []

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.script is not None:
            self.scripts.append("".join(self.script))
            self.script = None


def main():
    with tempfile.TemporaryDirectory(prefix="shim_review_regression_") as data_dir:
        os.environ["SHIM_DATA_DIR"] = data_dir
        os.environ.pop("SHIM_SECRET_KEY", None)
        from fastapi.testclient import TestClient
        from openpyxl import load_workbook
        from sqlalchemy.exc import IntegrityError
        from src.app import auth, database, models, utils
        from src.app.main import app
        from src.app.migrations import run_all_migrations
        from src.app.key_material import resolve_key_fingerprint
        from src.app.services import admin_service, leave_service, ops

        database.Base.metadata.create_all(database.engine)
        run_all_migrations(database.engine)
        clients = []

        def client(uid):
            result = TestClient(app)
            result.cookies.set("access_token", "Bearer " + auth.create_access_token({"sub": uid, "token_version": 0}))
            clients.append(result)
            return result

        def add_leave(uid, day, *, deductive=True):
            with database.SessionLocal() as db:
                leave = models.Leaves(user_id=uid, date=day, year=day.year, snapshot_slot_label="09:00~18:00",
                    snapshot_start_min=540, snapshot_end_min=1080, snapshot_deduction_hours=8,
                    status="PENDING", is_deductive=deductive, reason="검증")
                db.add(leave)
                db.commit()
                return leave.id

        def race(left, right):
            gate = Barrier(2)
            original = database.begin_write_transaction
            def synchronized(db):
                if not db.connection().connection.driver_connection.in_transaction:
                    gate.wait(timeout=10)
                original(db)
            with patch.object(database, "begin_write_transaction", synchronized):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    a, b = pool.submit(left), pool.submit(right)
                    responses = [a.result(timeout=40), b.result(timeout=40)]
            assert sorted(r.status_code for r in responses) == [200, 400], [(r.status_code, r.text) for r in responses]

        try:
            with database.SessionLocal() as db:
                for uid, role, hours, name in [
                    ("admin", "ADMIN", 0, "관리자"), ("staff", "STAFF", 120, "직원"),
                    ("lead", "TEAM_LEAD", 120, "팀장"), ("limited", "STAFF", 8, "한도"),
                    ("zero", "STAFF", 0, "O'Neil \"이름\""),
                ]:
                    db.add(models.Users(user_id=uid, user_name=name, role=role, company="C", team="T",
                        password="unused", total_leave_hours=hours, is_active=True))
                db.add(models.SystemSettings(is_approval_required=True,
                    key_hash_snapshot=resolve_key_fingerprint(database.DB_PATH.parent)))
                db.commit()
            admin, staff, lead, limited = [client(uid) for uid in ("admin", "staff", "lead", "limited")]
            marker = '<img src=x onerror="window.__shim_review=1">'
            response = staff.post("/api/user/leave", data={"date_str": "2027-02-01", "reason": marker})
            assert response.status_code == 200, response.text
            html = staff.get("/user/calendar?year=2027").text
            fn = html[html.index("function openTimelineActionModal("):html.index("async function cancelTimelineLeave(")]
            node = r"""
const vm = require('vm');
const elements = {};
const node = () => ({value:'', innerHTML:'', textContent:'', fields:{},
    querySelector(selector) { return this.fields[selector] ??= node(); }});
const document = {getElementById: id => elements[id] ??= node()};
const context = {document, window:{shimModal:{open(){}}}};
vm.createContext(context); vm.runInContext(INPUT.fn, context);
for (const status of ['PENDING','REJECTED']) {
    context.openTimelineActionModal(1, INPUT.marker, INPUT.marker, 'C', '2027-02-01', INPUT.marker, true, status, INPUT.marker, INPUT.marker, 'staff');
    const content = elements.actionModalContent;
    if (content.innerHTML.includes(INPUT.marker)) throw Error('HTML injection');
    if (content.querySelector('[data-detail="reason"]').textContent !== INPUT.marker) throw Error('reason lost');
    if (status === 'REJECTED' && !content.querySelector('[data-detail="rejection"]').textContent.includes(INPUT.marker)) throw Error('rejection lost');
}
for (const script of INPUT.scripts) new Function(script);
"""
            parser = PageParser()
            parser.feed(admin.get("/admin/users").text)
            button = next(b for b in parser.buttons if b.get("data-user-action") == "edit" and b.get("data-user-id") == "zero")
            assert button["data-name"] == "O'Neil \"이름\"" and "onclick" not in button
            subprocess.run(["node"], input="const INPUT=" + json.dumps({"fn": fn, "marker": marker, "scripts": parser.scripts}) + ";" + node, text=True, encoding="utf-8", check=True)
            print("[PASS] Stored text stays text; quoted names preserve valid JavaScript.")

            for other_action in ("cancel", "reject"):
                lid = add_leave("staff", date(2027, 2, 3 if other_action == "cancel" else 4))
                right = (lambda: staff.post(f"/api/user/leave/cancel/{lid}")) if other_action == "cancel" else (
                    lambda: lead.post(f"/api/user/team-reject/{lid}", data={"rejection_reason": "검증"}))
                race(lambda: lead.post(f"/api/user/team-approve/{lid}"), right)
                with database.SessionLocal() as db:
                    actions = db.query(models.AuditLogs).filter(models.AuditLogs.target_info.like(f"Leave:{lid} (%")).all()
                    assert len(actions) == 1, [a.action for a in actions]
            lid = add_leave("limited", date(2027, 2, 8), deductive=False)
            race(lambda: admin.post("/api/admin/leave/update-type", data={"leave_id": lid, "is_deductive": "true"}),
                lambda: limited.post("/api/user/leave", data={"date_str": "2027-02-09"}))
            with database.SessionLocal() as db:
                total = sum(x.snapshot_deduction_hours for x in db.query(models.Leaves).filter_by(user_id="limited", is_deductive=True))
                assert total == 8
            print("[PASS] Concurrent approval/cancel/reject and type/apply preserve state and quota.")

            r = admin.post("/api/admin/user/update", data={"target_user_id": "admin", "user_name": "관리자", "role": "STAFF"})
            assert r.status_code == 400
            assert admin.get("/admin/dashboard").status_code == 200
            with database.SessionLocal() as db:
                year = utils.get_business_now().year
                expected = sum(leave_service.resolve_user_yearly_allocated_hours(db, u, year)
                    for u in db.query(models.Users).filter(models.Users.role != "ADMIN"))
                assert admin_service.get_admin_dashboard_stats(db)["total_allocated_hours"] == expected
                assert sum(admin_service.get_admin_dashboard_charts_data(db, 2028)["remaining_hours"]) == 248
                db.add(models.UserYearlyLeaveAllocations(user_id="staff", year=2028, allocated_hours=0))
                db.commit()
                assert leave_service.resolve_user_yearly_allocated_hours(db, db.get(models.Users, "staff"), 2028) == 0
            result = admin.get("/admin/leave/timeline/export?year=2028")
            wb = load_workbook(io.BytesIO(result.content), read_only=True, data_only=True)
            try:
                rows = {r[0]: r for r in wb["연차 현황 요약"].iter_rows(values_only=True)}
                assert rows["zero"][7] == rows["staff"][7] == 0
                assert rows["lead"][7] == 120
            finally:
                wb.close()
            print("[PASS] Admin protection and allocation fallback/explicit zero agree.")

            for day, start, end, lunch_start, lunch_end, hours in [
                (10, 540, 1080, 420, 480, 9), (11, 0, 480, -1, -1, 8),
                (12, 960, 1440, -1, -1, 8), (15, 540, 1080, 480, 600, 8),
            ]:
                r = admin.post("/api/admin/settings/time-policy", data={"time_granularity_minutes": 60,
                    "work_start_minute": start, "work_end_minute": end,
                    "lunch_start_minute": lunch_start, "lunch_end_minute": lunch_end})
                assert r.status_code == 200, r.text
                r = staff.post("/api/user/leave", data={"date_str": f"2027-02-{day:02d}"})
                assert r.status_code == 200, r.text
                with database.SessionLocal() as db:
                    leave = db.query(models.Leaves).filter_by(user_id="staff", date=date(2027, 2, day)).one()
                    assert (leave.snapshot_start_min, leave.snapshot_end_min, leave.snapshot_deduction_hours) == (start, end, hours)
                assert admin.get("/api/admin/settings/approval").json()["work_start_minute"] == start
            print("[PASS] Outside/overlapping lunch and 00:00/24:00 policies preserve selected hours.")

            # 1. 설정 GET 표시 및 DB 불변 검증
            from sqlalchemy import inspect as sqla_inspect
            from src.app.routers.admin.settings import _get_system_setting_for_display, _normalize_setting_times

            with database.SessionLocal() as db:
                s = db.query(models.SystemSettings).first()
                s.product_display_name = "사용자 지정 프로젝트"
                s.product_nav_short = ""
                s.brand_initial = "P"
                s.time_granularity_minutes = 30
                s.work_start_minute = 0
                s.work_end_minute = 480
                s.lunch_start_minute = None
                s.lunch_end_minute = None
                s.team_calendar_visible = False
                s.company_calendar_visible = True
                db.commit()
                db.refresh(s)
                original_row_dict = {col.name: getattr(s, col.name) for col in models.SystemSettings.__table__.columns}
                original_updated_at = s.updated_at

            from sqlalchemy.orm import Session as SqlaSession
            commit_calls = 0
            flush_calls = 0
            orig_commit = SqlaSession.commit
            orig_flush = SqlaSession.flush

            def spy_commit(self, *a, **kw):
                nonlocal commit_calls
                commit_calls += 1
                return orig_commit(self, *a, **kw)

            def spy_flush(self, *a, **kw):
                nonlocal flush_calls
                flush_calls += 1
                return orig_flush(self, *a, **kw)

            with patch.object(SqlaSession, "commit", spy_commit), patch.object(SqlaSession, "flush", spy_flush):
                resp_json = admin.get("/api/admin/settings/approval")
                resp_html = admin.get("/admin/master")

            assert resp_json.status_code == 200
            assert resp_html.status_code == 200
            assert commit_calls == 0, f"Expected 0 commits during GET, got {commit_calls}"
            assert flush_calls == 0, f"Expected 0 flushes during GET, got {flush_calls}"

            j_data = resp_json.json()
            assert j_data["product_display_name"] == "사용자 지정 프로젝트"
            assert j_data["product_nav_short"] == ""
            assert j_data["brand_initial"] == "P"
            assert j_data["time_granularity_minutes"] == 30
            assert j_data["work_start_minute"] == 0
            assert j_data["work_end_minute"] == 480
            assert j_data["lunch_start_minute"] is None
            assert j_data["lunch_end_minute"] is None
            assert j_data["team_calendar_visible"] is False
            assert j_data["company_calendar_visible"] is True

            assert '<option value="0" selected>' in resp_html.text
            assert '<option value="480" selected>' in resp_html.text
            assert '<option value="30" selected>' in resp_html.text
            assert 'value="company" checked' in resp_html.text

            with database.SessionLocal() as db:
                s_after = db.query(models.SystemSettings).first()
                after_row_dict = {col.name: getattr(s_after, col.name) for col in models.SystemSettings.__table__.columns}
                assert original_row_dict == after_row_dict
                assert s_after.updated_at == original_updated_at

            with database.SessionLocal() as db:
                s = db.query(models.SystemSettings).first()
                s.work_start_minute = 541
                s.work_end_minute = 1079
                db.commit()

            resp = admin.get("/api/admin/settings/approval")
            assert resp.status_code == 200
            assert resp.json()["work_start_minute"] == 540
            assert resp.json()["work_end_minute"] == 1080
            with database.SessionLocal() as db:
                s = db.query(models.SystemSettings).first()
                assert s.work_start_minute == 541
                assert s.work_end_minute == 1079

            with database.SessionLocal() as db:
                s = db.query(models.SystemSettings).first()
                s.work_start_minute = 1080
                s.work_end_minute = 540
                db.commit()

            resp = admin.get("/api/admin/settings/approval")
            assert resp.status_code == 200
            assert resp.json()["work_start_minute"] == 540
            assert resp.json()["work_end_minute"] == 1080
            with database.SessionLocal() as db:
                s = db.query(models.SystemSettings).first()
                assert s.work_start_minute == 1080
                assert s.work_end_minute == 540

            with database.SessionLocal() as db:
                transient_inst = _get_system_setting_for_display(db)
                assert sqla_inspect(transient_inst).transient
                transient_inst.product_display_name = "임의 변경"
                staff_u = db.query(models.Users).filter_by(user_id="staff").first()
                staff_u.team = "T_TEMP"
                db.commit()
                raw_s = db.query(models.SystemSettings).first()
                assert raw_s.product_display_name != "임의 변경"
                staff_u.team = "T"
                db.commit()

            dummy_setting = models.SystemSettings(work_start_minute=None, work_end_minute=None, time_granularity_minutes=None)
            _normalize_setting_times(dummy_setting)
            assert dummy_setting.work_start_minute == 540
            assert dummy_setting.work_end_minute == 1080
            assert dummy_setting.time_granularity_minutes == 60

            with database.SessionLocal() as db:
                saved_settings_rows = [
                    {col.name: getattr(r, col.name) for col in models.SystemSettings.__table__.columns}
                    for r in db.query(models.SystemSettings).all()
                ]
                db.query(models.SystemSettings).delete()
                db.commit()

            with patch("src.app.routers.admin.settings.resolve_key_fingerprint", side_effect=AssertionError("resolve_key_fingerprint must not be called")):
                resp_empty_json = admin.get("/api/admin/settings/approval")
                resp_empty_html = admin.get("/admin/master")
            assert resp_empty_json.status_code == 200
            data_empty = resp_empty_json.json()
            assert data_empty["is_approval_required"] is False
            assert data_empty["time_granularity_minutes"] == 60
            assert data_empty["work_start_minute"] == 540
            assert data_empty["work_end_minute"] == 1080
            assert data_empty["lunch_start_minute"] == 720
            assert data_empty["lunch_end_minute"] == 780
            assert data_empty["product_display_name"] == "SHIM"
            assert data_empty["product_nav_short"] == ""
            assert data_empty["brand_initial"] == "S"
            assert data_empty["team_calendar_visible"] is True
            assert data_empty["company_calendar_visible"] is False
            assert resp_empty_html.status_code == 200

            with database.SessionLocal() as db:
                assert db.query(models.SystemSettings).count() == 0
                for row_data in saved_settings_rows:
                    db.add(models.SystemSettings(**row_data))
                db.commit()

            # 2. POST 설정 보존 검증 (branding 및 calendar-scope)
            r_brand = admin.post("/api/admin/settings/branding", data={
                "product_display_name": "신규 프로젝트명",
                "product_nav_short": "신규",
                "brand_initial": "N",
            })
            assert r_brand.status_code == 200
            with database.SessionLocal() as db:
                audit = db.query(models.AuditLogs).filter_by(action="UPDATE_BRANDING_SETTING").order_by(models.AuditLogs.id.desc()).first()
                assert audit is not None
                assert "display=신규 프로젝트명" in audit.new_data
                assert "nav_short=신규" in audit.new_data
                assert "initial=N" in audit.new_data

            with database.SessionLocal() as db:
                cached = leave_service.get_system_settings(db)
                assert cached.product_display_name == "신규 프로젝트명"

            r_scope = admin.post("/api/admin/settings/calendar-scope", data={"scope": "company"})
            assert r_scope.status_code == 200
            with database.SessionLocal() as db:
                audit = db.query(models.AuditLogs).filter_by(action="UPDATE_CALENDAR_SCOPE_SETTING").order_by(models.AuditLogs.id.desc()).first()
                assert audit is not None
                assert audit.new_data == "company"

            resp_scope_check = admin.get("/api/admin/settings/approval")
            assert resp_scope_check.json()["team_calendar_visible"] is True
            assert resp_scope_check.json()["company_calendar_visible"] is True

            # 3. 대시보드 부재자 시간 표시 및 이스케이프 검증
            today_date = utils.get_business_now().date()
            with database.SessionLocal() as db:
                db.add_all([
                    models.Leaves(user_id="staff", date=today_date, year=today_date.year,
                                  snapshot_slot_label="09:00~14:00", snapshot_start_min=540, snapshot_end_min=840,
                                  snapshot_deduction_hours=4, status="APPROVED", is_deductive=True, reason="오전 반차"),
                    models.Leaves(user_id="lead", date=today_date, year=today_date.year,
                                  snapshot_slot_label="15:00~16:00", snapshot_start_min=900, snapshot_end_min=960,
                                  snapshot_deduction_hours=1, status="APPROVED", is_deductive=False, reason="외출"),
                    models.Leaves(user_id="zero", date=today_date, year=today_date.year,
                                  snapshot_slot_label="", snapshot_start_min=540, snapshot_end_min=1080,
                                  snapshot_deduction_hours=8, status="APPROVED", is_deductive=True, reason="라벨 비어있음"),
                    models.Leaves(user_id="limited", date=today_date, year=today_date.year,
                                  snapshot_slot_label='<script>alert("xss")</script>', snapshot_start_min=540, snapshot_end_min=1080,
                                  snapshot_deduction_hours=8, status="APPROVED", is_deductive=True, reason="스크립트 라벨"),
                ])
                db.commit()

            dash_text = admin.get("/admin/dashboard").text
            assert "오늘 휴가/공가/출장자" in dash_text
            card_start = dash_text.index("오늘 휴가/공가/출장자")
            card_end = dash_text.index("최근 주요 활동 로그")
            card_html = dash_text[card_start:card_end]

            assert "09:00~14:00" in card_html
            assert "15:00~16:00" in card_html
            assert "시간 정보 없음" in card_html
            assert '<script>alert("xss")</script>' not in card_html
            assert "&lt;script&gt;alert(" in card_html
            assert "09:00 ~ 18:00" not in card_html

            with database.SessionLocal() as db:
                db.query(models.Leaves).filter(models.Leaves.date == today_date).delete()
                db.commit()

            good = ops.run_backup_and_rotate(database.DB_PATH, max_backups=1)
            assert ops.get_backup_recovery_status(database.DB_PATH)["latest_compatible"]
            with database.SessionLocal() as db:
                db.add(models.SystemSettings())
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                else:
                    raise AssertionError("duplicate implicit settings insert succeeded")
                db.add(models.SystemSettings(id=2))
                db.commit()
            bad = ops.run_backup_and_rotate(database.DB_PATH, max_backups=1)
            assert bad.exists() and good.exists(), "incompatible backup must not evict a compatible backup"
            recovery = ops.get_backup_recovery_status(database.DB_PATH)
            assert not recovery["latest_compatible"] and recovery["compatible_backup"] == good.name
            assert "설정이 중복" in admin.get("/admin/dashboard").text
            assert admin.get("/api/admin/settings/approval").status_code == 409
            assert admin.get("/admin/master").status_code == 409
            assert admin.post("/api/admin/settings/approval", data={"is_approval_required": "false"}).status_code == 409
            repaired = Path(data_dir) / "repaired.db"
            with sqlite3.connect(bad) as src, sqlite3.connect(repaired) as dest:
                src.backup(dest)
                dest.execute("DELETE FROM system_settings WHERE id != 1")
            src.close()
            dest.close()
            assert ops._validate_recovery_candidate(repaired, resolve_key_fingerprint(database.DB_PATH.parent))[0]
            print("[PASS] Duplicate settings detected; compatible backup retained; repaired copy validates.")

            # 4. 비상 초기화 CLI 검증 (격리된 복제 DB에서 subprocess 실행)
            with tempfile.TemporaryDirectory(prefix="shim_cli_test_") as cli_dir:
                cli_data_dir = Path(cli_dir)
                cli_db = cli_data_dir / "shim_internal.db"
                with sqlite3.connect(database.DB_PATH) as src, sqlite3.connect(cli_db) as dest:
                    src.backup(dest)

                with sqlite3.connect(cli_db) as conn:
                    row = conn.execute("SELECT password, token_version FROM users WHERE user_id = 'admin'").fetchone()
                    initial_hash, initial_token_version = row[0], row[1] or 0

                cli_env = os.environ.copy()
                cli_env["SHIM_DATA_DIR"] = str(cli_data_dir)
                cli_env.pop("SHIM_SECRET_KEY", None)

                # 4-1. 정상 성공 케이스
                proc_ok = subprocess.run(
                    [sys.executable, str(ROOT / "tools/scripts/emergency_reset_admin.py")],
                    env=cli_env,
                    capture_output=True,
                    text=True,
                )
                assert proc_ok.returncode == 0, f"stdout: {proc_ok.stdout}, stderr: {proc_ok.stderr}"
                assert "[성공]" in proc_ok.stdout

                with sqlite3.connect(cli_db) as conn:
                    row = conn.execute("SELECT password, token_version FROM users WHERE user_id = 'admin'").fetchone()
                    new_hash, new_token_version = row[0], row[1]
                    assert new_hash != initial_hash
                    assert auth.verify_password("0000", new_hash)
                    assert new_token_version == initial_token_version + 1

                    audit_row = conn.execute(
                        "SELECT actor_id, action, target_info, old_data, new_data FROM audit_logs WHERE action = 'RESET_ADMIN_PASSWORD' ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    assert audit_row == ("admin", "RESET_ADMIN_PASSWORD", "Admin:admin", "*****", "***** (Emergency Reset)")

                # 4-2. 관리자 없는 복제 DB 케이스
                no_admin_dir = cli_data_dir / "no_admin"
                no_admin_dir.mkdir()
                no_admin_db = no_admin_dir / "shim_internal.db"
                with sqlite3.connect(cli_db) as src, sqlite3.connect(no_admin_db) as dest:
                    src.backup(dest)
                with sqlite3.connect(no_admin_db) as conn:
                    conn.execute("DELETE FROM users WHERE user_id = 'admin'")
                    conn.commit()
                    initial_no_admin_audits = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action = 'RESET_ADMIN_PASSWORD'").fetchone()[0]

                cli_env_no_admin = os.environ.copy()
                cli_env_no_admin["SHIM_DATA_DIR"] = str(no_admin_dir)
                cli_env_no_admin.pop("SHIM_SECRET_KEY", None)

                proc_no_admin = subprocess.run(
                    [sys.executable, str(ROOT / "tools/scripts/emergency_reset_admin.py")],
                    env=cli_env_no_admin,
                    capture_output=True,
                    text=True,
                )
                assert proc_no_admin.returncode == 1, f"stdout: {proc_no_admin.stdout}, stderr: {proc_no_admin.stderr}"
                assert "[오류] 'admin' 계정이 존재하지 않습니다." in proc_no_admin.stdout

                with sqlite3.connect(no_admin_db) as conn:
                    count_after = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action = 'RESET_ADMIN_PASSWORD'").fetchone()[0]
                    assert count_after == initial_no_admin_audits

                # 4-3. 저장 실패 복제 DB 케이스 (trigger로 audit_logs abort 유도)
                fail_dir = cli_data_dir / "fail"
                fail_dir.mkdir()
                fail_db = fail_dir / "shim_internal.db"
                with sqlite3.connect(cli_db) as src, sqlite3.connect(fail_db) as dest:
                    src.backup(dest)
                with sqlite3.connect(fail_db) as conn:
                    conn.execute("""
                        CREATE TRIGGER fail_audit_insert BEFORE INSERT ON audit_logs
                        WHEN NEW.action = 'RESET_ADMIN_PASSWORD'
                        BEGIN
                            SELECT RAISE(ABORT, 'forced failure');
                        END;
                    """)
                    conn.commit()
                    admin_before = conn.execute("SELECT password, token_version FROM users WHERE user_id = 'admin'").fetchone()
                    audits_before = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]

                cli_env_fail = os.environ.copy()
                cli_env_fail["SHIM_DATA_DIR"] = str(fail_dir)
                cli_env_fail.pop("SHIM_SECRET_KEY", None)

                proc_fail = subprocess.run(
                    [sys.executable, str(ROOT / "tools/scripts/emergency_reset_admin.py")],
                    env=cli_env_fail,
                    capture_output=True,
                    text=True,
                )
                assert proc_fail.returncode == 1, f"stdout: {proc_fail.stdout}, stderr: {proc_fail.stderr}"
                assert "[오류] 초기화 중 문제가 발생했습니다." in proc_fail.stdout
                assert "forced failure" not in proc_fail.stdout
                assert "forced failure" not in proc_fail.stderr
                assert "shim_internal.db" not in proc_fail.stdout
                assert "shim_internal.db" not in proc_fail.stderr

                with sqlite3.connect(fail_db) as conn:
                    admin_after = conn.execute("SELECT password, token_version FROM users WHERE user_id = 'admin'").fetchone()
                    audits_after = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
                    assert admin_before == admin_after
                    assert audits_before == audits_after
        finally:
            for c in clients:
                c.close()
            database.engine.dispose()


if __name__ == "__main__":
    main()
