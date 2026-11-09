import json
import os
import subprocess
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
            admin = db.get(models.Users, "admin_test")
            if not admin:
                admin = models.Users(
                    user_id="admin_test",
                    user_name="Admin Test",
                    password=auth.get_password_hash("testpass123"),
                    role="ADMIN",
                    is_active=True,
                )
                db.add(admin)
            # Ensure single system setting
            settings = db.query(models.SystemSettings).all()
            if len(settings) > 1:
                for s in settings[1:]:
                    db.delete(s)
                db.commit()
            setting = db.query(models.SystemSettings).first()
            if not setting:
                setting = models.SystemSettings(id=1)
                db.add(setting)
            setting.time_granularity_minutes = 60
            setting.work_start_minute = 540
            setting.work_end_minute = 1080
            setting.lunch_start_minute = 720
            setting.lunch_end_minute = 780
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


def test_120_minute_granularity_time_options():
    with tempfile.TemporaryDirectory(prefix="shim_time_options_test_") as temp_dir:
        os.environ["SHIM_DATA_DIR"] = temp_dir
        os.environ.pop("SHIM_SECRET_KEY", None)

        from fastapi.testclient import TestClient
        from src.app import auth, database, models
        from src.app.main import app

        database.Base.metadata.create_all(bind=database.engine)
        db = database.SessionLocal()
        try:
            password_hash = auth.get_password_hash("0000")
            user = db.get(models.Users, "staff1")
            if not user:
                user = models.Users(
                    user_id="staff1",
                    user_name="Staff 1",
                    role="STAFF",
                    company="SHIM",
                    team="Dev",
                    password=password_hash,
                    total_leave_hours=120,
                    is_active=True,
                )
                db.add(user)
            # System settings with 120 minutes granularity
            from src.app.services.leave_policy import get_system_settings
            setting = db.query(models.SystemSettings).first()
            if not setting:
                setting = models.SystemSettings(id=1)
                db.add(setting)
            setting.time_granularity_minutes = 120
            setting.work_start_minute = 540
            setting.work_end_minute = 1080
            setting.lunch_start_minute = 720
            setting.lunch_end_minute = 780
            db.commit()
            get_system_settings(db, force_reload=True)

            token = auth.create_access_token({"sub": "staff1", "token_version": 0})
        finally:
            db.close()

        client = TestClient(app)
        client.cookies.set("access_token", f"Bearer {token}")

        # 1. Test calendar page (populates _add_user_layout_context)
        resp = client.get("/user/calendar?year=2026")
        assert resp.status_code == 200
        # In 120m granularity, 14:00 (half-day endpoint) must be an option in select
        assert '<option value="14:00"' in resp.text
        assert '<option value="09:00"' in resp.text
        assert '<option value="18:00"' in resp.text

        # 2. Test desktop-partial
        resp_partial = client.get("/user/calendar/desktop-partial?year=2026")
        assert resp_partial.status_code == 200
        assert '<option value="14:00"' in resp_partial.text

        # 3. Test team calendar desktop-partial
        resp_team_partial = client.get("/user/team-calendar/desktop-partial?year=2026&month=5")
        assert resp_team_partial.status_code == 200
        assert '<option value="14:00"' in resp_team_partial.text
        print("[PASS] 120-minute granularity time_options include half-day endpoints.")


def test_quick_apply_preset_runtime_and_dom():
    with tempfile.TemporaryDirectory(prefix="shim_quick_apply_test_") as temp_dir:
        os.environ["SHIM_DATA_DIR"] = temp_dir
        os.environ.pop("SHIM_SECRET_KEY", None)

        from fastapi.testclient import TestClient
        from src.app import auth, database, models
        from src.app.main import app

        database.Base.metadata.create_all(bind=database.engine)
        db = database.SessionLocal()
        try:
            password_hash = auth.get_password_hash("0000")
            user = db.get(models.Users, "staff_preset_test")
            if not user:
                user = models.Users(
                    user_id="staff_preset_test",
                    user_name="Staff Preset",
                    role="STAFF",
                    company="SHIM",
                    team="Dev",
                    password=password_hash,
                    total_leave_hours=120,
                    is_active=True,
                )
                db.add(user)
                db.commit()
            token = auth.create_access_token({"sub": "staff_preset_test", "token_version": 0})
        finally:
            db.close()

        client = TestClient(app)
        client.cookies.set("access_token", f"Bearer {token}")

        # 1. Desktop / mobile handler availability and architectural compliance
        shell_html = client.get("/user/calendar?year=2026").text
        # Handler availability on mobile shell (loaded once from base.html):
        assert "window.selectLeavePreset = selectLeavePreset" in shell_html
        assert "window.updateTimeSelectorAvailabilityG = updateTimeSelectorAvailabilityG" in shell_html
        assert "window.updateEstimatedTimeG = updateEstimatedTimeG" in shell_html
        assert "window.submitEasyApply = submitEasyApply" in shell_html
        assert 'id="easy-start-date-g_mobile"' in shell_html
        assert 'id="preset-full_mobile"' in shell_html
        assert 'id="preset-morning_mobile"' in shell_html
        assert 'id="preset-afternoon_mobile"' in shell_html
        assert 'id="preset-custom_mobile"' in shell_html
        # Architectural check: no innerHTML script re-execution hack
        assert "container.querySelectorAll('script').forEach" not in shell_html

        # Desktop partial availability and purity (no inline quick apply scripts):
        desktop_partial_html = client.get("/user/calendar/desktop-partial?year=2026").text
        assert 'id="easy-start-date-g_desktop"' in desktop_partial_html
        assert 'id="preset-full_desktop"' in desktop_partial_html
        assert 'id="preset-morning_desktop"' in desktop_partial_html
        assert 'id="preset-afternoon_desktop"' in desktop_partial_html
        assert 'id="preset-custom_desktop"' in desktop_partial_html
        assert "window.selectLeavePreset" not in desktop_partial_html

        # Team calendar shell & partial checks:
        team_shell_html = client.get("/user/team-calendar?year=2026&month=5").text
        assert "window.selectLeavePreset = selectLeavePreset" in team_shell_html
        assert "window.restoreTeamCalendarSelection = restoreTeamCalendarSelection" in team_shell_html
        assert "container.querySelectorAll('script').forEach" not in team_shell_html

        team_partial_html = client.get("/user/team-calendar/desktop-partial?year=2026&month=5").text
        assert 'id="easy-start-date-g_desktop"' in team_partial_html
        assert "window.selectLeavePreset" not in team_partial_html

        # 2. Node VM runtime behavior verification: extract script without brittle comment markers
        import re
        script_blocks = re.findall(r"<script[^>]*>([\s\S]*?)</script>", shell_html)
        quick_js = next(s for s in script_blocks if "window.selectLeavePreset = selectLeavePreset" in s)

        node_script = r"""
const vm = require('vm');
const assert = require('assert/strict');

class MockClassList {
    constructor() { this.classes = new Set(); }
    add(...cls) { cls.forEach(c => this.classes.add(c)); }
    remove(...cls) { cls.forEach(c => this.classes.delete(c)); }
    contains(c) { return this.classes.has(c); }
}

class MockElement {
    constructor(id = '') {
        this.id = id;
        this.value = '';
        this.textContent = '';
        this.disabled = false;
        this.attributes = {};
        this.classList = new MockClassList();
    }
    setAttribute(k, v) { this.attributes[k] = v; if (k === 'disabled') this.disabled = true; }
    removeAttribute(k) { delete this.attributes[k]; if (k === 'disabled') this.disabled = false; }
}

const elements = {};
function getEl(id) {
    if (!elements[id]) elements[id] = new MockElement(id);
    return elements[id];
}

const document = {
    getElementById: id => getEl(id),
};

const window = {
    shimWorkHours: { start: '09:00', end: '18:00' },
    shimTime: {
        parseDateOnly: s => {
            const [y, m, d] = s.split('-').map(Number);
            return new Date(y, m - 1, d);
        }
    },
    holidayMapDates: ['2026-05-05'],
};

const context = { console, document, window, setTimeout, clearTimeout };
vm.createContext(context);
vm.runInContext(INPUT.code, context);

// Test 1: Pre-date estimate behavior (empty dates)
const calcEl = getEl('easy-calc-g_mobile');
const startEl = getEl('easy-start-g_mobile');
const endEl = getEl('easy-end-g_mobile');
startEl.value = '09:00'; endEl.value = '18:00';

context.window.updateEstimatedTimeG('mobile');
assert.ok(calcEl.textContent.includes('전일 (1일 / 8시간)'), 'Default pre-date should show 8h, got ' + calcEl.textContent);
assert.ok(!calcEl.textContent.includes('0시간'), 'Pre-date estimate must not be 0시간');

// Morning preset pre-date
context.window.selectLeavePreset('mobile', 'morning');
assert.ok(calcEl.textContent.includes('오전 반차 (0.5일)'), 'Morning preset pre-date should show morning half-day');

// Afternoon preset pre-date
context.window.selectLeavePreset('mobile', 'afternoon');
assert.ok(calcEl.textContent.includes('오후 반차 (0.5일)'), 'Afternoon preset pre-date should show afternoon half-day');

// Test 2: Custom 4h range behavior (Argon finding 3)
// 10:00 to 15:00 has lunch (12:00-13:00) excluded -> 4 hours deduction
startEl.value = '10:00'; endEl.value = '15:00';
context.window.updateEstimatedTimeG('mobile');
assert.ok(calcEl.textContent.includes('4시간'), 'Custom 4h range must display hours, got ' + calcEl.textContent);
assert.ok(!calcEl.textContent.includes('반차'), 'Custom 4h range must NOT be labeled as morning/afternoon half-day');

// Single-day custom 4h range: 13:00 to 17:00 (4 hours)
const startDateInput = getEl('easy-start-date-g_mobile');
const endDateInput = getEl('easy-end-date-g_mobile');
startDateInput.value = '2026-06-01';
endDateInput.value = '2026-06-01';
startEl.value = '13:00'; endEl.value = '17:00';
context.window.updateEstimatedTimeG('mobile');
assert.ok(calcEl.textContent.includes('4시간'), 'Single day custom 4h range must display 4시간, got ' + calcEl.textContent);
assert.ok(!calcEl.textContent.includes('반차'), 'Single day custom 4h range must NOT be labeled as 반차');

// Exact morning slot on single day
startEl.value = '09:00'; endEl.value = '14:00';
context.window.updateEstimatedTimeG('mobile');
assert.ok(calcEl.textContent.includes('오전 반차 (0.5일)'), 'Exact morning slot must show 오전 반차 (0.5일)');

// Exact afternoon slot on single day
startEl.value = '14:00'; endEl.value = '18:00';
context.window.updateEstimatedTimeG('mobile');
assert.ok(calcEl.textContent.includes('오후 반차 (0.5일)'), 'Exact afternoon slot must show 오후 반차 (0.5일)');

// Test 3: Custom preset highlight
context.window.selectLeavePreset('mobile', 'custom');
assert.ok(getEl('preset-custom_mobile').classList.contains('bg-dense-blue'), 'Custom button should be active');
assert.ok(!getEl('easy-time-row_mobile').classList.contains('hidden'), 'Time row should be visible in custom');
// When updateEstimatedTimeG runs again, custom must stay highlighted!
context.window.updateEstimatedTimeG('mobile');
assert.ok(getEl('preset-custom_mobile').classList.contains('bg-dense-blue'), 'Custom button must stay highlighted after estimate update');
assert.ok(!getEl('preset-full_mobile').classList.contains('bg-dense-blue'), 'Full button must NOT steal highlight in custom');

// Test 4: Multi-day preset state/control
startDateInput.value = '2026-06-01';
endDateInput.value = '2026-06-03';

context.window.updateTimeSelectorAvailabilityG('mobile');
assert.ok(getEl('preset-morning_mobile').disabled, 'Morning preset button must be disabled for multi-day');
assert.ok(getEl('preset-afternoon_mobile').disabled, 'Afternoon preset button must be disabled for multi-day');
assert.ok(getEl('preset-custom_mobile').disabled, 'Custom preset button must be disabled for multi-day');
assert.ok(getEl('preset-full_mobile').classList.contains('bg-dense-blue'), 'Multi-day must force full preset');

// Returning to single day re-enables buttons
endDateInput.value = '2026-06-01';
context.window.updateTimeSelectorAvailabilityG('mobile');
assert.equal(getEl('preset-morning_mobile').disabled, false, 'Morning button re-enabled on single day');
assert.equal(getEl('preset-afternoon_mobile').disabled, false, 'Afternoon button re-enabled on single day');

// Test 5: Local date key timezone issue
// 2026-05-04 to 2026-05-06: 2026-05-05 is a holiday in holidayMapDates
startDateInput.value = '2026-05-04';
endDateInput.value = '2026-05-06';
context.window.updateEstimatedTimeG('mobile');
assert.ok(calcEl.textContent.includes('2일'), 'May 4-6 with May 5 holiday should be 2 workdays, got ' + calcEl.textContent);
"""

        subprocess.run(
            ["node"],
            input="const INPUT=" + json.dumps({"code": quick_js}) + ";" + node_script,
            text=True,
            encoding="utf-8",
            check=True,
        )

        # 3. Team calendar restoration runtime verification
        team_script_blocks = re.findall(r"<script[^>]*>([\s\S]*?)</script>", team_shell_html)
        team_js = next(s for s in team_script_blocks if "window.restoreTeamCalendarSelection = restoreTeamCalendarSelection" in s)

        team_node_script = r"""
const vm = require('vm');
const assert = require('assert/strict');

class MockElement {
    constructor(id = '') {
        this.id = id;
        this.value = '';
        this.classList = {
            classes: new Set(),
            add(...c) { c.forEach(x => this.classes.add(x)); },
            remove(...c) { c.forEach(x => this.classes.delete(x)); },
            contains(x) { return this.classes.has(x); }
        };
    }
}

const elements = {};
function getEl(id) {
    if (!elements[id]) elements[id] = new MockElement(id);
    return elements[id];
}

const document = {
    getElementById: id => getEl(id),
    querySelectorAll: () => [],
    addEventListener: () => {},
};

const storage = {
    'shim_timeline_start_date': '2026-06-02',
    'shim_timeline_end_date': '2026-06-05',
};

const sessionStorage = {
    getItem: k => storage[k] || null,
    setItem: (k, v) => { storage[k] = v; },
    removeItem: k => { delete storage[k]; },
};

let availabilityCheckedDesktop = false;
let availabilityCheckedMobile = false;

const onAvailability = prefix => {
    if (prefix === 'desktop') availabilityCheckedDesktop = true;
    if (prefix === 'mobile') availabilityCheckedMobile = true;
};

const window = {
    parseLocalDate: s => new Date(s),
    matchMedia: () => ({ matches: true, addEventListener: () => {} }),
    updateTimeSelectorAvailabilityG: onAvailability,
};

const context = {
    console,
    document,
    window,
    sessionStorage,
    setTimeout,
    clearTimeout,
    isBusinessDay: () => true,
    getDatesInRange: (s, e) => [s, e],
    highlightSelectedDates: () => {},
    updateFloatingBar: () => {},
    toggleMultiSelectMode: () => {},
    updateTimeSelectorAvailabilityG: onAvailability,
};

vm.createContext(context);
vm.runInContext(INPUT.code, context);

// Execute team restoration
context.window.restoreTeamCalendarSelection();

assert.equal(getEl('easy-start-date-g_desktop').value, '2026-06-02', 'Desktop start date must be restored');
assert.equal(getEl('easy-end-date-g_desktop').value, '2026-06-05', 'Desktop end date must be restored');
assert.equal(getEl('easy-start-date-g_mobile').value, '2026-06-02', 'Mobile start date must be restored');
assert.equal(getEl('easy-end-date-g_mobile').value, '2026-06-05', 'Mobile end date must be restored');
assert.ok(availabilityCheckedDesktop, 'updateTimeSelectorAvailabilityG(desktop) should be called');
assert.ok(availabilityCheckedMobile, 'updateTimeSelectorAvailabilityG(mobile) should be called');
"""
        subprocess.run(
            ["node"],
            input="const INPUT=" + json.dumps({"code": team_js}) + ";" + team_node_script,
            text=True,
            encoding="utf-8",
            check=True,
        )
        print("[PASS] Quick apply preset runtime, DOM, timezone, and multi-day controls verified.")
        print("[PASS] Team calendar desktop sessionStorage restoration verified.")


if __name__ == "__main__":
    test_allowed_granularities()
    test_resolve_half_day_slots_default_work_hours()
    test_resolve_half_day_slots_without_lunch()
    test_half_day_snapshot_deduction()
    test_half_day_rejects_arbitrary_ranges()
    test_half_day_preset_allowed_in_other_granularities()
    test_admin_settings_time_policy_endpoint()
    test_120_minute_granularity_time_options()
    test_quick_apply_preset_runtime_and_dom()
    print("[PASS] test_half_day_policy passed successfully.")
