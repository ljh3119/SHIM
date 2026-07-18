from datetime import date
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.app import utils


def main():
    holidays_2025 = {}
    utils.add_constitution_day_holidays(holidays_2025, 2025)
    assert date(2025, 7, 17) not in holidays_2025

    holidays_2026 = {}
    utils.add_constitution_day_holidays(holidays_2026, 2026)
    assert holidays_2026 == {date(2026, 7, 17): "제헌절"}

    holidays_2027 = {}
    utils.add_constitution_day_holidays(holidays_2027, 2027)
    assert holidays_2027[date(2027, 7, 17)] == "제헌절"
    assert holidays_2027[date(2027, 7, 19)] == "제헌절 대체공휴일"

    print("[PASS] 2026년 이후 제헌절 및 대체공휴일 생성 확인")


if __name__ == "__main__":
    main()
