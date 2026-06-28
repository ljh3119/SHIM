from functools import lru_cache
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


# ==============================================================================
# [이중 폴백(Double Fallback) 설계 포인트]
# 본 애플리케이션은 환경변수 누락 시에도 한국 표준시(KST) 기준 동작을 보장하기 위해
# 1) Python 코드 레벨(아래 헬퍼 함수 기본값)과
# 2) 인프라 설정 레벨(docker-compose.yml의 ${VAR:-default} 문법)
# 양쪽에 모두 기본값(Asia/Seoul 및 9.0)을 이중 폴백으로 하드코딩하여 심층 방어하고 있습니다.
# 향후 타 국가로 기본 시간대를 영구 이전하고자 할 때는 이 두 영역의 기본값을 모두 갱신해야 합니다.
# ==============================================================================


@lru_cache(maxsize=1)
def get_timezone_offset_hours() -> float:
    import os
    env_val = os.getenv("SHIM_TIMEZONE_OFFSET_HOURS")
    if env_val is not None:
        try:
            return float(env_val)
        except ValueError:
            pass
    # 환경변수 누락 시 기본값으로 9.0 (KST) 고정 반환하여 시스템 안정성 보장
    return 9.0


def clear_timezone_cache():
    """테스트 등 환경 변수 변경 시 타임존 오프셋 캐시를 무효화합니다."""
    get_timezone_offset_hours.cache_clear()


def local_to_utc_naive(dt):
    """
    Timezone-aware datetime 객체를 Naive UTC datetime 객체로 변환하여 반환합니다.
    입력이 Naive인 경우, get_timezone_offset_hours()를 기준으로 로컬 타임존을 임베딩하여 UTC로 변환합니다.
    None인 경우 None을 반환합니다.
    """
    if dt is None:
        return None
    import datetime
    
    if dt.tzinfo is None:
        offset = get_timezone_offset_hours()
        local_tz = datetime.timezone(datetime.timedelta(hours=offset))
        dt = dt.replace(tzinfo=local_tz)
        
    return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)

def to_kst(dt):
    if dt is None:
        return None
    import datetime
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    offset = get_timezone_offset_hours()
    local_tz = datetime.timezone(datetime.timedelta(hours=offset))
    return dt.astimezone(local_tz)

def to_kst_naive(dt):
    kst_dt = to_kst(dt)
    if kst_dt is None:
        return None
    return kst_dt.replace(tzinfo=None)

def format_datetime_kst(dt, fmt='%Y-%m-%d %H:%M'):
    kst_dt = to_kst(dt)
    if kst_dt is None:
        return ""
    return kst_dt.strftime(fmt)


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


def get_local_now():
    import datetime
    offset = get_timezone_offset_hours()
    local_tz = datetime.timezone(datetime.timedelta(hours=offset))
    return datetime.datetime.now(datetime.timezone.utc).astimezone(local_tz)


def get_local_today() -> str:
    return get_local_now().strftime("%Y-%m-%d")

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




