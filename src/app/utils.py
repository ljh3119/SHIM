import datetime
import os
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError


def add_constitution_day_holidays(holiday_map, year: int) -> None:
    """Backfill Constitution Day until python-holidays includes the 2026 change."""
    constitution_day = datetime.date(year, 7, 17)
    if year < 2026 or constitution_day in holiday_map:
        return

    holiday_map[constitution_day] = "제헌절"
    if constitution_day.weekday() < 5:
        return

    substitute = constitution_day + datetime.timedelta(days=1)
    while substitute.weekday() >= 5 or substitute in holiday_map:
        substitute += datetime.timedelta(days=1)
    holiday_map[substitute] = "제헌절 대체공휴일"


def sanitize_excel_text(value) -> str:
    """Prevent user-controlled text from being interpreted as an Excel formula."""
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else text


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
    return [(minute, f"{minute // 60:02d}:{minute % 60:02d}") for minute in range(0, 24 * 60 + 1, 30)]


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

    prefix = "-" if th < 0 else ""
    value = abs(th)
    days = int(value // day_hours)
    remainder = round(value - days * day_hours, 1)
    remainder = int(remainder) if abs(remainder - int(remainder)) < 1e-9 else remainder

    if days > 0:
        return f"{prefix}{days}일" + (f"{remainder}h" if remainder > 0 else "")
    return f"{prefix}{remainder}h" if remainder > 0 else "-"


# 쌍자음(ㄲ, ㄷ, ㅃ, ㅆ, ㅉ)을 포함한 표준 초성 목록
CHOSUNG_LIST = [
    'ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'
]

def get_chosung(text: str) -> str:
    chosung = []
    for char in text:
        code = ord(char)
        if 0xAC00 <= code <= 0xD7A3:
            idx = ((code - 0xAC00) // 28) // 21
            chosung.append(CHOSUNG_LIST[idx])
        else:
            chosung.append(char)
    return "".join(chosung)

def search_users_stateless(users_list: list, query_str: str) -> list:
    """
    제공된 사용자 목록에 대해 초성/부분 일치 인메모리 검색을 수행합니다.
    """
    if not query_str or not query_str.strip():
        return users_list

    query_clean = query_str.strip().lower()
    
    # 쌍자음을 포함한 정밀 초성 판별식
    is_pure_chosung = all(char in CHOSUNG_LIST for char in query_clean)

    results = []
    for u in users_list:
        name = getattr(u, "user_name", "") if hasattr(u, "user_name") else u.get("user_name", "")
        name_lower = name.lower()
        chosung_name = get_chosung(name)
        
        if is_pure_chosung and query_clean in chosung_name:
            results.append(u)
        elif not is_pure_chosung and query_clean in name_lower:
            results.append(u)
    return results


@lru_cache(maxsize=1)
def get_business_timezone_name() -> str:
    return os.getenv("SHIM_TIMEZONE", "Asia/Seoul").strip() or "Asia/Seoul"


@lru_cache(maxsize=1)
def get_business_timezone() -> ZoneInfo:
    name = get_business_timezone_name()
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"Invalid SHIM_TIMEZONE: {name}") from exc


def clear_timezone_cache():
    get_business_timezone.cache_clear()
    get_business_timezone_name.cache_clear()


def to_business_time(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(get_business_timezone())


def to_business_naive(dt):
    business_dt = to_business_time(dt)
    if business_dt is None:
        return None
    return business_dt.replace(tzinfo=None)


def format_datetime_business(dt, fmt='%Y-%m-%d %H:%M'):
    business_dt = to_business_time(dt)
    if business_dt is None:
        return ""
    return business_dt.strftime(fmt)

# 회사 색상: 보조적이지만 서로 확실히 구분될 수 있도록 엄선된 8가지 웜톤/녹색계열 색상 목록 (0~140도 범위)
# (hue, saturation, bg_lightness, text_lightness)
COMPANY_COLORS = [
    (12, 70, 91, 24),   # Coral / Red-Orange
    (24, 65, 90, 22),   # Terracotta / Warm Orange
    (38, 75, 90, 20),   # Bronze / Amber
    (52, 75, 89, 18),   # Yellow-Gold
    (72, 55, 90, 20),   # Chartreuse / Lime
    (95, 45, 90, 20),   # Sage Green
    (120, 48, 90, 18),  # Forest Green
    (138, 45, 90, 18),  # Mint Green
]

def string_to_badge_style(text: str, is_team: bool = False) -> str:
    if not text or text == "—" or not text.strip():
        return "background-color: var(--dense-surface-soft); color: var(--dense-muted); border: 1px solid var(--dense-line);"
    
    # 해싱 전 고유 접두사를 결합하여 회사와 팀의 해시 씨앗 분리
    prefix = "team:" if is_team else "company:"
    salted_text = prefix + text
    
    h = 0
    for char in salted_text:
        h = ord(char) + ((h << 5) - h)
    
    if is_team:
        # 팀: 더 확실히 봐야 하므로 생동감 있고 강렬한 대역 (파랑, 보라, 마젠타, 핑크: 180 ~ 340도)
        hsl_hue = 180 + (abs(h) % 160)
        hsl_s = 75
        hsl_bg_l = 91
        hsl_text_l = 15
        
        fallback_bg = f"background-color: hsl({hsl_hue}, {hsl_s}%, {hsl_bg_l}%);"
        fallback_color = f"color: hsl({hsl_hue}, {hsl_s + 5}%, {hsl_text_l}%);"
        fallback_border = f"border: 1px solid hsl({hsl_hue}, {hsl_s - 10}%, {hsl_bg_l - 4}%);"
        
        # OKLCH 적용 (지각 균일 명도 보장)
        oklch_hue = hsl_hue
        oklch_bg = f"background-color: oklch(0.92 0.09 {oklch_hue});"
        oklch_color = f"color: oklch(0.25 0.09 {oklch_hue});"
        oklch_border = f"border: 1px solid oklch(0.87 0.08 {oklch_hue});"
        
        return f"{fallback_bg} {fallback_color} {fallback_border} {oklch_bg} {oklch_color} {oklch_border}"
    else:
        # 회사: 팀 색상(180~340도)과 겹치지 않는 0~140도 범위 내에서 엄선된 색상 매핑
        color_idx = abs(h) % len(COMPANY_COLORS)
        hsl_hue, hsl_s, hsl_bg_l, hsl_text_l = COMPANY_COLORS[color_idx]
        
        fallback_bg = f"background-color: hsl({hsl_hue}, {hsl_s}%, {hsl_bg_l}%);"
        fallback_color = f"color: hsl({hsl_hue}, {hsl_s + 5}%, {hsl_text_l}%);"
        fallback_border = f"border: 1px solid hsl({hsl_hue}, {hsl_s - 10}%, {hsl_bg_l - 4}%);"
        
        # OKLCH 적용
        oklch_hue = hsl_hue
        oklch_bg = f"background-color: oklch(0.91 0.07 {oklch_hue});"
        oklch_color = f"color: oklch(0.22 0.07 {oklch_hue});"
        oklch_border = f"border: 1px solid oklch(0.86 0.06 {oklch_hue});"
        
        return f"{fallback_bg} {fallback_color} {fallback_border} {oklch_bg} {oklch_color} {oklch_border}"


def get_business_now():
    return datetime.datetime.now(datetime.timezone.utc).astimezone(get_business_timezone())


def get_business_today() -> datetime.date:
    return get_business_now().date()

def get_business_date_bounds_utc(day: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    business_tz = get_business_timezone()
    start = datetime.datetime.combine(day, datetime.time.min, tzinfo=business_tz)
    end = datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time.min, tzinfo=business_tz)
    return start.astimezone(datetime.timezone.utc), end.astimezone(datetime.timezone.utc)

def create_notification(db, user_id: str, sender_id: str | None, message: str):
    from . import models
    n = models.Notifications(
        user_id=user_id,
        sender_id=sender_id,
        message=message,
        is_read=False
    )
    db.add(n)
    return n


def validate_password_strength(password: str) -> str | None:
    """
    KISA (한국인터넷진흥원) 비밀번호 가이드라인에 따른 복잡성 검증:
    1) 최소 8자 이상
    2) 영문, 숫자, 특수문자 중 2종류 이상 조합 시 10자 이상
    3) 영문, 숫자, 특수문자 3종류 모두 조합 시 8자 이상
    4) 공백(space) 금지
    """
    from .auth import BCRYPT_MAX_PASSWORD_BYTES
    if len(password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        return "비밀번호는 UTF-8 기준 72바이트 이하여야 합니다. 한글·이모지는 여러 바이트를 사용합니다."

    if " " in password:
        return "비밀번호에 공백을 포함할 수 없습니다."
    
    length = len(password)
    if length < 8:
        return "비밀번호는 최소 8자 이상이어야 합니다."
        
    import re
    has_letter = 1 if re.search(r'[a-zA-Z]', password) else 0
    has_digit = 1 if re.search(r'[0-9]', password) else 0
    # 특수문자 정의: 공백 제외 비알파뉴메릭
    has_special = 1 if re.search(r'[^a-zA-Z0-9]', password) else 0
    
    types_count = has_letter + has_digit + has_special
    
    if types_count < 2:
        return "비밀번호는 영문, 숫자, 특수문자 중 2종류 이상을 혼용해야 합니다."
        
    if types_count == 2 and length < 10:
        return "2종류 조합 시 비밀번호는 10자 이상이어야 합니다. (3종류 모두 조합 시 8자 이상)"
        
    return None


def mask_name(name: str) -> str:
    """
    이름 개인정보 마스킹 처리 헬퍼 함수:
    - Null 또는 빈 문자열: "" 반환
    - 1글자: 그대로 반환 (예: "A" -> "A")
    - 2글자: 홍길 -> 홍*
    - 3글자: 홍길동 -> 홍*동
    - 4글자 이상 한글: 제임스허 -> 제**허
    - 공백이 있는 이름(영문 등): 단어별로 나누어 각각 마스킹 후 재조립 (예: "John Doe" -> "J**n D*e")
    """
    if not name:
        return ""
    name_str = str(name).strip()
    if not name_str:
        return ""
    
    # 공백이 포함된 이름의 경우 (예: "John Doe", "Hong Gil Dong")
    if " " in name_str:
        parts = name_str.split(" ")
        masked_parts = [mask_name(p) for p in parts if p]
        return " ".join(masked_parts)
        
    length = len(name_str)
    if length <= 1:
        return name_str
    if length == 2:
        return name_str[0] + "*"
    if length == 3:
        return name_str[0] + "*" + name_str[2]
    return name_str[0] + "*" * (length - 2) + name_str[-1]




