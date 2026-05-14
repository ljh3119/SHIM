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

    def _fmt(d: int, rem: int, neg: bool) -> str:
        pre = "-" if neg else ""
        if d > 0 and rem > 0:
            return f"{pre}{d}일{rem}h"
        if d > 0 and rem == 0:
            return f"{pre}{d}일"
        if d == 0 and rem > 0:
            return f"{pre}{rem}h"
        return "-"

    if th < 0:
        t = abs(th)
        d = int(t // day_hours)
        rem = int(round(t - d * day_hours))
        return _fmt(d, rem, True)
    d = int(th // day_hours)
    rem = int(round(th - d * day_hours))
    return _fmt(d, rem, False)
