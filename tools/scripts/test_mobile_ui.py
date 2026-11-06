from __future__ import annotations

import json
import os
import subprocess
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

            js_start = calendar_shell.text.index("let mobileCalendarYearG")
            js_end = calendar_shell.text.index("async function loadCalendarDesktopG()")
            mobile_js = calendar_shell.text[js_start:js_end]

            node_mobile_race_test = r"""
const vm = require('vm');
const assert = require('assert/strict');

class MockElement {
  constructor(tag = 'div', id = '') {
    this.tagName = tag.toUpperCase();
    this.id = id;
    this.value = '';
    this.textContent = '';
    this.children = [];
    this.listeners = {};
    this.classList = { add() {}, remove() {}, contains: () => false };
  }
  appendChild(c) { this.children.push(c); return c; }
  replaceChildren(...items) {
    this.children = items.flatMap(item => item.tagName === 'FRAGMENT' ? item.children : [item]);
  }
  addEventListener(ev, fn) { (this.listeners[ev] ??= []).push(fn); }
  click() { for (const fn of this.listeners.click || []) fn(); }
  findButton(txt) {
    if (this.tagName === 'BUTTON' && (this.textContent || '').includes(txt)) return this;
    for (const c of this.children) {
      const found = c.findButton?.(txt);
      if (found) return found;
    }
    return null;
  }
}

const elements = {
  'mobile-calendar-year-g': new MockElement('select', 'mobile-calendar-year-g'),
  'mobile-calendar-month-g': new MockElement('select', 'mobile-calendar-month-g'),
  'mobile-calendar-grid-g': new MockElement('div', 'mobile-calendar-grid-g'),
};
const modalCalls = [];
let pending = [];

const makePayload = (month, id = month * 100 + 1) => ({
  year: 2024, month, days_in_month: 30, offset: 1, holidays: {},
  days: { '1': [{ id, slot_label: '09:00~18:00', deduction_hours: 8, is_deductive: true, status: 'APPROVED', reason: `${month}월` }] }
});
const makeResponse = data => ({ ok: true, status: 200, json: async () => data });

const context = {
  console, URL,
  document: {
    getElementById: id => elements[id] ??= new MockElement('div', id),
    createElement: tag => new MockElement(tag),
    createDocumentFragment: () => new MockElement('fragment'),
  },
  window: {
    location: new URL('https://example.test/user/calendar?year=2024&month=2'),
    history: { replaceState(s, t, url) { context.window.location = new URL(url.toString(), 'https://example.test'); } },
    matchMedia: () => ({ matches: false })
  },
  fetch: url => new Promise((resolve, reject) => pending.push({ url, resolve, reject })),
  openTimelineActionModal: (id, u, t, c, dateStr) => modalCalls.push({ type: 'timeline', id, dateStr }),
  openCalendarApplyModal: dateStr => modalCalls.push({ type: 'apply', dateStr }),
};
vm.createContext(context);
vm.runInContext(INPUT.code, context);

const run = code => vm.runInContext(code, context);
const getState = () => run('({ year: mobileCalendarYearG, month: mobileCalendarMonthG, data: mobileCalendarDataG, loaded: mobileCalendarLoadedG })');

(async () => {
  // 1. 연속 2회 moveMobileCalendarMonthG(1) 호출 (2개월 이동 회귀 방지)
  run('mobileCalendarYearG = 2024; mobileCalendarMonthG = 2;');
  pending = [];
  run('moveMobileCalendarMonthG(1)');
  assert.equal(pending.length, 1);
  assert.ok(pending[0].url.includes('month=3'));
  assert.equal(getState().month, 3, '1차 이동 시 3월 갱신');

  run('moveMobileCalendarMonthG(1)');
  assert.equal(pending.length, 2);
  assert.ok(pending[1].url.includes('month=4'));
  assert.equal(getState().month, 4, '연속 호출 시 4월 갱신 (2개월 이동)');

  // 2. 역순 성공: 4월(최신) 먼저 완료 후 3월(이전) 완료 -> 4월 데이터 유지
  pending[1].resolve(makeResponse(makePayload(4)));
  await Promise.resolve();
  await new Promise(r => setImmediate(r));
  assert.equal(getState().month, 4);
  assert.equal(getState().data.month, 4);
  assert.equal(getState().data.days['1'][0].id, 401);
  assert.equal(getState().loaded, true);
  assert.equal(elements['mobile-calendar-month-g'].value, '4');

  pending[0].resolve(makeResponse(makePayload(3)));
  await Promise.resolve();
  await new Promise(r => setImmediate(r));
  assert.equal(getState().month, 4, '오래된 3월 응답 후에도 4월 선택 월 유지');
  assert.equal(getState().data.month, 4, '오래된 3월 응답 후에도 4월 데이터 유지');
  assert.equal(getState().data.days['1'][0].id, 401, '4월 연차 ID 유지');

  // 3. 오래된 실패: 5월 요청 후 6월 요청 -> 6월 성공 후 5월 실패 -> 6월 화면 및 URL 유지, 오류/재시도 버튼 미발생
  pending = [];
  const p5 = run('loadMobileCalendarG(2024, 5)');
  const p6 = run('loadMobileCalendarG(2024, 6)');
  pending[1].resolve(makeResponse(makePayload(6)));
  await p6;

  const gridChildrenBefore = [...elements['mobile-calendar-grid-g'].children];
  const urlBefore = context.window.location.searchParams.get('month');
  assert.equal(urlBefore, '6', '최신 성공 응답의 월을 URL에 반영');
  assert.ok(gridChildrenBefore.length > 0, '6월 날짜 버튼 렌더링 확인');

  pending[0].reject(new Error('Old network error'));
  await p5;

  assert.equal(elements['mobile-calendar-grid-g'].findButton('다시 시도'), null, '오래된 실패로 재시도 버튼이 생성되지 않음');
  assert.equal(elements['mobile-calendar-grid-g'].children.length, gridChildrenBefore.length, '화면 그리드가 오류 메시지로 대체되지 않음');
  assert.equal(context.window.location.searchParams.get('month'), urlBefore, 'URL 파라미터 유지');
  assert.equal(elements['mobile-calendar-month-g'].value, '6');
  assert.equal(getState().month, 6, '오래된 실패 무시 후 6월 선택 월 유지');
  assert.equal(getState().data.month, 6, '6월 데이터 유지');
  assert.equal(getState().data.days['1'][0].id, 601, '6월 연차 ID 유지');
  assert.equal(getState().loaded, true);

  // 4. 지연된 JSON: 7월 fetch 완료 후 json 대기 중 -> 8월 전체 완료 -> 7월 json 완료 시 8월 유지
  pending = [];
  const p7 = run('loadMobileCalendarG(2024, 7)');
  const p8 = run('loadMobileCalendarG(2024, 8)');
  let resolveJson7;
  pending[0].resolve({ ok: true, status: 200, json: () => new Promise(res => { resolveJson7 = res; }) });
  pending[1].resolve(makeResponse(makePayload(8)));
  await p8;
  assert.equal(getState().month, 8);
  resolveJson7(makePayload(7));
  await p7;
  assert.equal(getState().month, 8, '지연된 JSON 도착 후 8월 선택 월 유지');
  assert.equal(getState().data.month, 8, '8월 데이터 유지');
  assert.equal(getState().data.days['1'][0].id, 801, '8월 연차 ID 유지');

  // 5. 최신 실패와 재시도: 최신 9월 실패 -> 재시도 버튼 클릭 -> 9월 재요청 및 성공 반영
  pending = [];
  const p9 = run('loadMobileCalendarG(2024, 9)');
  pending[0].reject(new Error('500 Error'));
  await p9;
  assert.equal(getState().loaded, false);
  assert.equal(getState().data, null);
  const retryBtn = elements['mobile-calendar-grid-g'].findButton('다시 시도');
  assert.ok(retryBtn, '다시 시도 버튼 렌더링 확인');

  pending = [];
  retryBtn.click();
  assert.equal(pending.length, 1, '재시도 새 fetch 발생');
  assert.ok(pending[0].url.includes('month=9'), '실패했던 9월로 재요청');
  pending[0].resolve(makeResponse(makePayload(9)));
  await Promise.resolve();
  await new Promise(r => setImmediate(r));
  assert.equal(getState().month, 9, '재시도 성공 후 9월 반영');
  assert.equal(getState().data.month, 9, '9월 데이터 반영');
  assert.equal(getState().loaded, true);

  // 6. 날짜 클릭 및 연차 ID 일치, 로딩 중 클릭 차단
  modalCalls.length = 0;
  run('openMobileCalendarDayG(1, false)');
  assert.equal(modalCalls.length, 1);
  assert.equal(modalCalls[0].id, 901, '연차 ID 일치');
  assert.equal(modalCalls[0].dateStr, '2024-09-01', '날짜 일치');

  pending = [];
  const p10 = run('loadMobileCalendarG(2024, 10)');
  assert.equal(getState().data, null, '로딩 시작 시 데이터 초기화');
  assert.equal(getState().loaded, false, '로딩 시작 시 loaded 초기화');
  modalCalls.length = 0;
  run('openMobileCalendarDayG(1, false)');
  assert.equal(modalCalls.length, 0, '로딩 중 클릭은 무시됨');

  pending[0].resolve(makeResponse(makePayload(10)));
  await p10;
  modalCalls.length = 0;
  run('openMobileCalendarDayG(1, false)');
  assert.equal(modalCalls.length, 1);
  assert.equal(modalCalls[0].id, 1001, '10월 완료 후 연차 ID 일치');
  assert.equal(modalCalls[0].dateStr, '2024-10-01', '10월 완료 후 날짜 일치');
})().catch(err => {
  console.error(err);
  process.exitCode = 1;
});
"""
            subprocess.run(
                ["node"],
                input="const INPUT=" + json.dumps({"code": mobile_js}) + ";\n" + node_mobile_race_test,
                text=True,
                encoding="utf-8",
                check=True,
            )

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
