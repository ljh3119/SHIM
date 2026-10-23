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
            assert admin.post("/api/admin/settings/approval", data={"is_approval_required": "false"}).status_code == 409
            repaired = Path(data_dir) / "repaired.db"
            with sqlite3.connect(bad) as src, sqlite3.connect(repaired) as dest:
                src.backup(dest)
                dest.execute("DELETE FROM system_settings WHERE id != 1")
            src.close()
            dest.close()
            assert ops._validate_recovery_candidate(repaired, resolve_key_fingerprint(database.DB_PATH.parent))[0]
            print("[PASS] Duplicate settings detected; compatible backup retained; repaired copy validates.")
        finally:
            for c in clients:
                c.close()
            database.engine.dispose()


if __name__ == "__main__":
    main()
