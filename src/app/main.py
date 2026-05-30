from fastapi import FastAPI, Depends, Request, Form, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date, timedelta
import os
import sys
from pathlib import Path
import holidays
from contextlib import asynccontextmanager

from . import models, database, auth
from .database import engine, get_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_event()
    yield
    
    # Shutdown: 임시 바구니 비우기(체크포인트) 수행 후 커넥션 풀 해제
    db = database.SessionLocal()
    try:
        db.execute(text("PRAGMA wal_checkpoint(TRUNCATE);"))
        print("[SHIM] Database wal_checkpoint(TRUNCATE) completed successfully on shutdown.")
    except Exception as e:
        print(f"[SHIM ERROR] Database wal_checkpoint failed on shutdown: {e}")
    finally:
        db.close()
        
    database.engine.dispose()
    print("[SHIM] Lifespan shutdown: Database connection pool disposed successfully.")

app = FastAPI(title="SHIM", version="1.5.19", lifespan=lifespan)

DEFAULT_PRODUCT_DISPLAY_NAME = "쉼(SHIM) 프로젝트 개발 운영"
DEFAULT_BRAND_INITIAL = "S"
BRANDING_BADGE_MAX_LEN = 24


VALID_ROLES = frozenset({"STAFF", "TEAM_LEAD", "PM", "ADMIN"})





models.Base.metadata.create_all(bind=engine)

# 자동 스키마 마이그레이션
from .migrations import run_all_migrations
try:
    run_all_migrations(engine)
except Exception as e:
    print(f"[MIGRATION ERROR] Schema migration failed: {e}")





def _normalize_branding_from_row(row: models.SystemSettings | None) -> dict[str, str | bool]:
    if row is None:
        display = DEFAULT_PRODUCT_DISPLAY_NAME
        nav_raw_stored = ""
        nav_short = display
        badge = DEFAULT_BRAND_INITIAL
    else:
        display = (getattr(row, "product_display_name", None) or "").strip() or DEFAULT_PRODUCT_DISPLAY_NAME
        nav_raw_stored = (getattr(row, "product_nav_short", None) or "").strip()
        nav_short = nav_raw_stored if nav_raw_stored else display
        raw_initial = (getattr(row, "brand_initial", None) or "").strip()
        if raw_initial:
            badge = raw_initial[:BRANDING_BADGE_MAX_LEN]
        else:
            badge = (display[:1] if display else DEFAULT_BRAND_INITIAL) or DEFAULT_BRAND_INITIAL
    show_subtitle = display != nav_short
    return {
        "product_display_name": display,
        "product_nav_short": nav_short,
        "product_nav_short_raw": nav_raw_stored,
        "brand_nav_show_subtitle": show_subtitle,
        "brand_initial": badge,
        "brand_badge_display": badge,
    }


from .services.leave_policy import get_system_settings

def _load_branding_into_request(request: Request) -> None:
    db = database.SessionLocal()
    try:
        row = get_system_settings(db)
        b = _normalize_branding_from_row(row)
        request.state.product_display_name = b["product_display_name"]
        request.state.product_nav_short = b["product_nav_short"]
        request.state.product_nav_short_raw = b["product_nav_short_raw"]
        request.state.brand_nav_show_subtitle = b["brand_nav_show_subtitle"]
        request.state.brand_initial = b["brand_initial"]
        request.state.brand_badge_display = b["brand_badge_display"]
    finally:
        db.close()


def branding_template_context(request: Request) -> dict:
    return {
        "product_display_name": getattr(request.state, "product_display_name", DEFAULT_PRODUCT_DISPLAY_NAME),
        "product_nav_short": getattr(request.state, "product_nav_short", DEFAULT_PRODUCT_DISPLAY_NAME),
        "product_nav_short_raw": getattr(request.state, "product_nav_short_raw", ""),
        "brand_nav_show_subtitle": getattr(request.state, "brand_nav_show_subtitle", False),
        "brand_initial": getattr(request.state, "brand_initial", DEFAULT_BRAND_INITIAL),
        "brand_badge_display": getattr(request.state, "brand_badge_display", DEFAULT_BRAND_INITIAL),
        "is_default_password": getattr(request.state, "is_default_password", False),
    }

def _resolve_runtime_base() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    if not getattr(sys, "frozen", False):
        src_base = project_root / "src"
        if (src_base / "templates").exists() and (src_base / "static").exists():
            return src_base
        return project_root

    # PyInstaller frozen: find bundled templates/static (exe dir, _internal, _MEIPASS, etc.).
    exe_dir = Path(sys.executable).resolve().parent
    candidates: list[Path] = []
    env_base = os.getenv("SHIM_RUNTIME_BASE")
    if env_base:
        candidates.append(Path(env_base))
    candidates.append(exe_dir / "_internal")
    candidates.append(exe_dir)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass))
    candidates.append(Path.cwd())

    for base in candidates:
        if (base / "templates").exists() and (base / "static").exists():
            return base
        if (base / "src" / "templates").exists() and (base / "src" / "static").exists():
            return base / "src"
    # No bundle path matched; default to PyInstaller _internal layout.
    return exe_dir / "_internal"


runtime_base = _resolve_runtime_base()
templates_dir = runtime_base / "templates"
static_dir = runtime_base / "static"

if not templates_dir.exists() or not static_dir.exists():
    raise RuntimeError(
        "Portable resource path is invalid. "
        f"runtime_base={runtime_base}, "
        f"templates_exists={templates_dir.exists()}, "
        f"static_exists={static_dir.exists()}"
    )

print(f"[SHIM] runtime_base={runtime_base}")
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(
    directory=str(templates_dir),
    context_processors=[branding_template_context],
)
def string_to_hsl_style(text: str, is_team: bool = False) -> str:
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
        hue = 180 + (abs(h) % 160)
        s = 75
        bg_l = 91
        text_l = 15
    else:
        # 회사: 보조적인 정보이므로 은은하고 차분한 대역 (주황, 노랑, 초록, 청록: 20 ~ 180도)
        hue = 20 + (abs(h) % 160)
        s = 52
        bg_l = 95
        text_l = 32

    # 노란색, 라임색 등 가시성이 취약한 45~95도 구간 보정
    if 45 <= hue <= 95:
        if is_team:
            bg_l = 88
            text_l = 10
        else:
            bg_l = 93
            text_l = 22
        
    return f"background-color: hsl({hue}, {s}%, {bg_l}%); color: hsl({hue}, {s + 5}%, {text_l}%); border: 1px solid hsl({hue}, {s - 10}%, {bg_l - 4}%);"

templates.env.globals["app_version"] = "1.5.19"
templates.env.globals["min"] = min
templates.env.globals["max"] = max
templates.env.globals["string_to_hsl_style"] = string_to_hsl_style
app.state.templates = templates

from .routers import api_user, api_admin
from .dependencies import NotAuthenticatedException, PermissionDeniedException
from fastapi.responses import JSONResponse

@app.exception_handler(NotAuthenticatedException)
async def not_authenticated_exception_handler(request: Request, exc: NotAuthenticatedException):
    path = request.url.path
    if path.startswith("/static/") or path.startswith("/docs") or path == "/openapi.json" or path == "/favicon.ico":
        return Response(status_code=404)
    if path.startswith("/api/"):
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

@app.exception_handler(PermissionDeniedException)
async def permission_denied_exception_handler(request: Request, exc: PermissionDeniedException):
    path = request.url.path
    if path.startswith("/static/") or path.startswith("/docs") or path == "/openapi.json" or path == "/favicon.ico":
        return Response(status_code=404)
    if path.startswith("/api/"):
        return JSONResponse(status_code=401, content={"detail": "Permission denied"})
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

app.include_router(api_user.page_router)
app.include_router(api_user.api_router)
app.include_router(api_admin.page_router)
app.include_router(api_admin.api_router)


@app.middleware("http")
async def branding_middleware(request: Request, call_next):
    p = request.url.path
    if p.startswith("/static") or p == "/favicon.ico":
        return await call_next(request)
    await run_in_threadpool(_load_branding_into_request, request)
    return await call_next(request)


def _compact_kr_holiday_name(name: str) -> str:
    """Normalize Korean holiday names to compact labels."""
    compact_map = {
        "\uc124\ub0a0 \uc5f0\ud734": "\uc124 \uc5f0\ud734",
        "\ucd94\uc11d \uc5f0\ud734": "\ucd94\uc11d \uc5f0\ud734",
    }
    normalized = str(name).strip()
    return compact_map.get(normalized, normalized)


def seed_korean_holidays(db: Session, actor_id: str, start_year: int = 2020, end_year: int = 2050):
    # Keep per-year seed log so admin-edited holidays are not re-seeded.
    seeded_year_actions = {
        row[0]
        for row in db.query(models.AuditLogs.action)
        .filter(models.AuditLogs.action.like("SEED_KR_HOLIDAYS_%"))
        .all()
    }

    for year in range(start_year, end_year + 1):
        action_name = f"SEED_KR_HOLIDAYS_{year}"
        if action_name in seeded_year_actions:
            continue

        kr_holidays = holidays.country_holidays("KR", years=[year], language="ko")
        for holiday_date, holiday_name in kr_holidays.items():
            normalized_name = _compact_kr_holiday_name(holiday_name)
            exists = db.query(models.Holidays).filter(models.Holidays.date == holiday_date).first()
            if not exists:
                db.add(models.Holidays(name=normalized_name, date=holiday_date))

        # python-holidays KR seed may miss Labor Day (May 1); add fallback.
        labor_day = date(year, 5, 1)
        if not db.query(models.Holidays).filter(models.Holidays.date == labor_day).first():
            db.add(models.Holidays(name="\ub178\ub3d9\uc808", date=labor_day))

        db.add(
            models.AuditLogs(
                actor_id=actor_id,
                action=action_name,
                target_info=f"HolidaySeed:{year}",
                old_data="None",
                new_data="KR holiday seed incl. May 1 Labor Day",
            )
        )


def startup_event():
    db = database.SessionLocal()
    try:
        try:
            db.execute(text("PRAGMA wal_checkpoint(TRUNCATE);"))
        except Exception as e:
            print(f"[SHIM WARNING] Database wal_checkpoint failed on startup: {e}")
            
        try:
            check_res = db.execute(text("PRAGMA quick_check;")).fetchall()
            if not check_res or check_res[0][0] != "ok":
                print(f"[SHIM DATABASE CORRUPT WARNING] 물리적 데이터 정합성 검사 실패: {check_res}")
                print("[SHIM DATABASE CORRUPT WARNING] 데이터베이스 파일이 비정상 종료 등으로 손상되었을 수 있습니다.")
                print("[SHIM DATABASE CORRUPT WARNING] 데이터 복구가 필요한 경우, 최근 핫 백업 파일(.bak)로 복구를 시도하십시오.")
        except Exception as check_err:
            print(f"[SHIM DATABASE CORRUPT WARNING] 자가 무결성 검사 중 에러 발생: {check_err}")
            
        admin = db.query(models.Users).filter(models.Users.user_id == "admin").first()
        if not admin:
            hashed_pw = auth.get_password_hash("0000")
            new_admin = models.Users(
                user_id="admin",
                user_name="시스템관리자",
                password=hashed_pw,
                is_admin=True,
                role="ADMIN",
            )
            db.add(new_admin)
            db.commit()
            admin = new_admin
        elif not admin.user_name or "?" in admin.user_name:
            admin.user_name = "시스템관리자"

        if not db.query(models.SystemSettings).first():
            db.add(
                models.SystemSettings(
                    is_approval_required=False,
                    time_granularity_minutes=60,
                    work_start_minute=9 * 60,
                    work_end_minute=18 * 60,
                    product_display_name=DEFAULT_PRODUCT_DISPLAY_NAME,
                    product_nav_short="",
                    brand_initial=DEFAULT_BRAND_INITIAL,
                    team_calendar_visible=True,
                    company_calendar_visible=False,
                )
            )
        else:
            db.execute(
                text(
                    """
                    UPDATE system_settings
                    SET time_granularity_minutes = COALESCE(time_granularity_minutes, 60),
                        work_start_minute = COALESCE(work_start_minute, 540),
                        work_end_minute = COALESCE(work_end_minute, 1080),
                        team_calendar_visible = COALESCE(team_calendar_visible, 1),
                        company_calendar_visible = COALESCE(company_calendar_visible, 0)
                    """
                )
            )

        seed_korean_holidays(db=db, actor_id=admin.user_id, start_year=2020, end_year=2050)
        db.commit()
    finally:
        db.close()


@app.get("/", response_class=HTMLResponse)
def read_root(request: Request, db: Session = Depends(get_db)):
    user_id = auth.get_current_user_from_token(request)
    if user_id:
        user = db.query(models.Users).filter(models.Users.user_id == user_id).first()
        if user:
            user_role = getattr(user, "role", "STAFF")
            if user_role == "ADMIN":
                return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_302_FOUND)
            return RedirectResponse(url="/user/dashboard", status_code=status.HTTP_302_FOUND)
    
    return templates.TemplateResponse(request=request, name="login.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)

@app.post("/login")
def login(
        request: Request,
        user_id: str = Form(...),
        password: str = Form(...),
        db: Session = Depends(get_db)
):
    user_id = user_id.strip()
    user = db.query(models.Users).filter(models.Users.user_id == user_id).first()
    if not user or not auth.verify_password(password, user.password):
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "\uc544\uc774\ub514 \ub610\ub294 \ube44\ubc00\ubc88\ud638\uac00 \uc798\ubabb\ub418\uc5c8\uc2b5\ub2c8\ub2e4."})
    if not user.is_active:
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "\ube44\ud65c\uc131\ud654\ub41c \uacc4\uc815\uc785\ub2c8\ub2e4."})
    
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={
            "sub": user.user_id,
            "token_version": user.token_version,
            "is_default_password": password == "0000"
        },
        expires_delta=access_token_expires
    )
    
    cookie_settings = auth.get_cookie_settings(request)
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        **cookie_settings
    )
    return response

@app.get("/logout")
def logout(request: Request):
    cookie_settings = auth.get_cookie_settings(request)
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(
        key="access_token",
        httponly=cookie_settings.get("httponly", True),
        samesite=cookie_settings.get("samesite", "lax"),
        secure=cookie_settings.get("secure", False)
    )
    return response

