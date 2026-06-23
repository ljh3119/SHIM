import os
import unittest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from src.app.utils import get_timezone_offset_hours, clear_timezone_cache, local_to_utc_naive

class TestTimezoneUtils(unittest.TestCase):
    """utils.py에 신규 반영된 타임존 오프셋 캐싱 및 Naive UTC 변환 유틸리티를 검증하는 테스트 스위트"""

    def setUp(self):
        # 각 테스트 실행 전 캐시를 강제로 비워 독립성 보장
        clear_timezone_cache()
        # 환경변수 임시 백업 및 정리
        self.orig_env = os.environ.get("SHIM_TIMEZONE_OFFSET_HOURS")
        if "SHIM_TIMEZONE_OFFSET_HOURS" in os.environ:
            del os.environ["SHIM_TIMEZONE_OFFSET_HOURS"]

    def tearDown(self):
        # 환경변수 원래 상태로 복구
        if self.orig_env is not None:
            os.environ["SHIM_TIMEZONE_OFFSET_HOURS"] = self.orig_env
        else:
            if "SHIM_TIMEZONE_OFFSET_HOURS" in os.environ:
                del os.environ["SHIM_TIMEZONE_OFFSET_HOURS"]
        clear_timezone_cache()

    @patch("os.getenv")
    def test_timezone_offset_caching(self, mock_getenv):
        """get_timezone_offset_hours 호출 시 LRU 캐시가 정상 동작하여 반복 조회를 방지하는지 검증"""
        mock_getenv.return_value = "9.0"

        # 1. 최초 호출 시: 환경 변수 조회가 실제로 1회 발생해야 함
        offset1 = get_timezone_offset_hours()
        self.assertEqual(offset1, 9.0)
        self.assertEqual(mock_getenv.call_count, 1)

        # 2. 반복 호출 시: 캐시에 적재된 값을 O(1)로 반환하므로 getenv 시스템 콜이 추가 발생하지 않음
        offset2 = get_timezone_offset_hours()
        self.assertEqual(offset2, 9.0)
        self.assertEqual(mock_getenv.call_count, 1)

    @patch("os.getenv")
    def test_clear_timezone_cache(self, mock_getenv):
        """clear_timezone_cache 호출 시 캐시가 비워지고 바뀐 환경 변수 값이 새롭게 반영되는지 검증"""
        mock_getenv.return_value = "9.0"

        # 최초 호출로 캐시 적재
        get_timezone_offset_hours()
        self.assertEqual(mock_getenv.call_count, 1)

        # 캐시 비우기
        clear_timezone_cache()

        # 환경 변수 반환값 동적 시뮬레이션 변경
        mock_getenv.return_value = "10.0"

        # 캐시가 비워졌으므로 함수가 새로 평가되어 갱신된 오프셋 반영 확인
        offset = get_timezone_offset_hours()
        self.assertEqual(offset, 10.0)
        self.assertEqual(mock_getenv.call_count, 2)

    def test_local_to_utc_naive_with_aware_dt(self):
        """Timezone-aware datetime 객체를 전달했을 때 타임존 정보를 버리고 순수 Naive UTC 시간으로 변환하는지 검증"""
        local_tz = timezone(timedelta(hours=9)) # KST (+09:00) 기준
        aware_dt = datetime(2026, 6, 4, 12, 0, 0, tzinfo=local_tz)

        # 12:00 KST -> 03:00 UTC
        utc_naive = local_to_utc_naive(aware_dt)
        self.assertIsNone(utc_naive.tzinfo) # Timezone-naive 형태 검증
        self.assertEqual(utc_naive, datetime(2026, 6, 4, 3, 0, 0))

    def test_local_to_utc_naive_with_naive_dt_and_leap_year(self):
        """Naive datetime 객체 전달 시, 로컬 타임존 시차를 가정하여 정상적으로 UTC 역산(윤년 경계 포함)하는지 검증"""
        # 타임존 오프셋 고정 (+09:00)
        os.environ["SHIM_TIMEZONE_OFFSET_HOURS"] = "9.0"
        clear_timezone_cache()

        # 윤년 2024년 2월 29일 새벽 5시 KST (Naive)
        # KST가 UTC보다 9시간 빠르므로 역산 시 2024년 2월 28일 20:00 UTC로 날짜가 바뀌어야 함
        naive_dt = datetime(2024, 2, 29, 5, 0, 0)
        
        utc_naive = local_to_utc_naive(naive_dt)
        self.assertIsNone(utc_naive.tzinfo)
        self.assertEqual(utc_naive, datetime(2024, 2, 28, 20, 0, 0))

    def test_local_to_utc_naive_none_input(self):
        """None을 입력했을 때 에러를 유발하지 않고 안전하게 None을 리턴하는지 검증"""
        self.assertIsNone(local_to_utc_naive(None))

