import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.app.models import AwareDateTime
from src.app.services.ops import get_next_notification_cleanup_run
from src.app.utils import (
    clear_timezone_cache,
    get_business_date_bounds_utc,
    get_business_timezone,
    get_business_timezone_name,
    to_business_time,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestTimezoneContract(unittest.TestCase):
    def setUp(self):
        self.original_timezone = os.environ.pop("SHIM_TIMEZONE", None)
        clear_timezone_cache()

    def tearDown(self):
        if self.original_timezone is None:
            os.environ.pop("SHIM_TIMEZONE", None)
        else:
            os.environ["SHIM_TIMEZONE"] = self.original_timezone
        clear_timezone_cache()

    def set_timezone(self, name: str):
        os.environ["SHIM_TIMEZONE"] = name
        clear_timezone_cache()

    def test_default_timezone_is_cached_as_asia_seoul(self):
        self.assertEqual(get_business_timezone_name(), "Asia/Seoul")
        self.assertEqual(get_business_timezone().key, "Asia/Seoul")
        os.environ["SHIM_TIMEZONE"] = "America/New_York"
        self.assertEqual(get_business_timezone().key, "Asia/Seoul")

    def test_new_york_dst_offsets_are_zoneinfo_based(self):
        self.set_timezone("America/New_York")
        winter = to_business_time(datetime(2026, 1, 15, 17, tzinfo=timezone.utc))
        summer = to_business_time(datetime(2026, 7, 15, 16, tzinfo=timezone.utc))
        self.assertEqual(winter.hour, 12)
        self.assertEqual(winter.utcoffset(), timedelta(hours=-5))
        self.assertEqual(summer.hour, 12)
        self.assertEqual(summer.utcoffset(), timedelta(hours=-4))

    def test_invalid_iana_timezone_fails_app_startup(self):
        env = os.environ.copy()
        env["SHIM_TIMEZONE"] = "Not/A_Real_Zone"
        env["SHIM_DATA_DIR"] = tempfile.mkdtemp(prefix="shim_invalid_tz_")
        result = subprocess.run(
            [sys.executable, "-c", "from src.app.main import app"],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid SHIM_TIMEZONE: Not/A_Real_Zone", result.stderr + result.stdout)

    def test_aware_datetime_stores_utc_and_rejects_naive(self):
        column_type = AwareDateTime()
        new_york = datetime(2026, 7, 14, 9, 30, tzinfo=timezone(timedelta(hours=-4)))
        stored = column_type.process_bind_param(new_york, None)
        self.assertEqual(stored, datetime(2026, 7, 14, 13, 30))
        self.assertIsNone(stored.tzinfo)

        loaded = column_type.process_result_value(stored, None)
        self.assertEqual(loaded, datetime(2026, 7, 14, 13, 30, tzinfo=timezone.utc))
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            column_type.process_bind_param(datetime(2026, 7, 14, 9, 30), None)

    def test_business_date_bounds_cover_kst_and_dst_days(self):
        self.set_timezone("Asia/Seoul")
        start, end = get_business_date_bounds_utc(date(2026, 7, 14))
        self.assertEqual(start, datetime(2026, 7, 13, 15, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 7, 14, 15, tzinfo=timezone.utc))

        self.set_timezone("America/New_York")
        spring_start, spring_end = get_business_date_bounds_utc(date(2026, 3, 8))
        fall_start, fall_end = get_business_date_bounds_utc(date(2026, 11, 1))
        self.assertEqual(spring_end - spring_start, timedelta(hours=23))
        self.assertEqual(fall_end - fall_start, timedelta(hours=25))

    def test_cleanup_scheduler_handles_normal_gap_and_duplicate_wall_times(self):
        self.set_timezone("Asia/Seoul")
        normal = get_next_notification_cleanup_run(datetime(2026, 7, 13, 16, tzinfo=timezone.utc))
        self.assertEqual(normal, datetime(2026, 7, 13, 17, tzinfo=timezone.utc))

        self.set_timezone("America/New_York")
        gap = get_next_notification_cleanup_run(datetime(2026, 3, 8, 5, tzinfo=timezone.utc))
        self.assertEqual(gap.astimezone(get_business_timezone()).hour, 3)

        self.set_timezone("Europe/Berlin")
        duplicate = get_next_notification_cleanup_run(datetime(2026, 10, 24, 22, tzinfo=timezone.utc))
        self.assertEqual(duplicate, datetime(2026, 10, 25, 0, tzinfo=timezone.utc))
        self.assertEqual(duplicate.astimezone(get_business_timezone()).fold, 0)

    def test_templates_do_not_append_z_or_convert_to_browser_timezone(self):
        templates = PROJECT_ROOT / "src" / "templates"
        html = "\n".join(path.read_text(encoding="utf-8") for path in templates.rglob("*.html"))
        self.assertNotIn("isoString + 'Z'", html)
        self.assertNotIn("isoformat() }}Z", html)
        self.assertNotIn("convertAllUtcElements", html)
        self.assertNotIn("data-utc=", html)
        self.assertIn("Number.isNaN(date.getTime())", html)

    def test_date_only_parser_keeps_western_browser_calendar_date(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required for the date-only browser regression test")
        module_path = json.dumps(str(PROJECT_ROOT / "src" / "static" / "js" / "time.js"))
        script = (
            f"require({module_path});"
            "const d=globalThis.shimTime.parseDateOnly('2026-07-14');"
            "process.stdout.write(d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0'));"
        )
        env = os.environ.copy()
        env["TZ"] = "America/Los_Angeles"
        result = subprocess.run([node, "-e", script], env=env, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "2026-07-14")


if __name__ == "__main__":
    unittest.main()