from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

def format_db_error_message(exc: Exception) -> str:
    if isinstance(exc, IntegrityError):
        return "데이터베이스 정합성 제약 조건 위반이 발생했습니다. (중복 등록 또는 연관 데이터 오류)"
    elif isinstance(exc, OperationalError):
        err_msg = str(exc).lower()
        if "locked" in err_msg or "timeout" in err_msg:
            return "데이터베이스가 다른 작업으로 인해 일시적으로 잠겨 있습니다. 잠시 후 다시 시도해 주세요."
        return "데이터베이스 입출력 또는 시스템 설정상의 오류가 발생했습니다."
    return f"데이터베이스 처리 중 오류가 발생했습니다. (상세: {type(exc).__name__})"

def build_year_options(now_year: int, data_years=None, past_span: int = 5, future_span: int = 10):
    years = [y for y in (data_years or []) if y is not None]
    min_data_year = min(years) if years else now_year
    max_data_year = max(years) if years else now_year
    start = min(now_year - past_span, min_data_year)
    end = max(now_year + future_span, max_data_year)
    return list(range(start, end + 1))


def build_minute_options(start_minute: int, end_minute: int, step_minute: int) -> list[str]:
    options: list[str] = []
    cursor = start_minute
    while cursor <= end_minute:
        hh = cursor // 60
        mm = cursor % 60
        options.append(f"{hh:02d}:{mm:02d}")
        cursor += step_minute
    if options:
        end_label = f"{end_minute // 60:02d}:{end_minute % 60:02d}"
        if options[-1] != end_label:
            options.append(end_label)
    return options


def build_half_hour_options() -> list[tuple[int, str]]:
    options: list[tuple[int, str]] = []
    minute = 0
    while minute <= 24 * 60:
        hh = minute // 60
        mm = minute % 60
        label = f"{hh:02d}:{mm:02d}"
        options.append((minute, label))
        minute += 30
    return options


def hours_to_days_hours_label(total_hours: float, day_hours: int = 8) -> str:
    th = float(total_hours) if total_hours is not None else 0.0
    if abs(th) < 1e-9:
        return "0일 0시간"
    negative = th < 0
    t = abs(th)
    days = int(t // day_hours)
    rem = t - days * day_hours
    rem_display = int(round(rem)) if abs(rem - round(rem)) < 1e-6 else round(rem, 1)
    if negative:
        if days > 0:
            return f"-{days}일 {rem_display}시간"
        return f"-{rem_display}시간"
    return f"{days}일 {rem_display}시간"


def hours_to_days_hours_compact(total_hours: float, day_hours: int = 8) -> str:
    th = float(total_hours) if total_hours is not None else 0.0
    if abs(th) < 1e-9:
        return "-"

    def _fmt(d: int, rem: float, neg: bool) -> str:
        pre = "-" if neg else ""
        if abs(rem - int(rem)) < 1e-9:
            rem_val = int(rem)
        else:
            rem_val = round(rem, 1)

        if d > 0 and rem_val > 0:
            return f"{pre}{d}일{rem_val}h"
        if d > 0 and rem_val == 0:
            return f"{pre}{d}일"
        if d == 0 and rem_val > 0:
            return f"{pre}{rem_val}h"
        return "-"

    if th < 0:
        t = abs(th)
        d = int(t // day_hours)
        rem = round(t - d * day_hours, 1)
        return _fmt(d, rem, True)
    d = int(th // day_hours)
    rem = round(th - d * day_hours, 1)
    return _fmt(d, rem, False)
