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

import asyncio
from . import models, database, auth, utils
from .database import engine, get_db, DB_PATH
from .services.ops import verify_and_recover_db, daily_backup_scheduler, notification_cleanup_scheduler, update_system_metrics_in_db
from .constants import APP_VERSION, VALID_ROLES

START_TIME = utils.get_local_now()

@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_event()
    backup_task = asyncio.create_task(daily_backup_scheduler(DB_PATH))
    cleanup_task = asyncio.create_task(notification_cleanup_scheduler())
    yield
    
    backup_task.cancel()
    cleanup_task.cancel()
    try:
        await asyncio.gather(backup_task, cleanup_task, return_exceptions=True)
    except Exception:
        pass
    
    # Shutdown: 커넥션 풀 해제 (SQLite가 커넥션 종료 시 자동으로 WAL 병합 및 정리 수행)
    database.engine.dispose()
    print("[SHIM] Lifespan shutdown: Database connection pool disposed successfully.")

app = FastAPI(title="SHIM", version=APP_VERSION, lifespan=lifespan)

from .middlewares.cors import ClosedNetworkCORSMiddleware

cors_origins_raw = os.getenv("SHIM_CORS_ORIGINS")
if cors_origins_raw:
    app.add_middleware(
        ClosedNetworkCORSMiddleware,
        origins_raw=cors_origins_raw
    )

DEFAULT_PRODUCT_DISPLAY_NAME = "쉼(SHIM) 프로젝트 개발 운영"
DEFAULT_BRAND_INITIAL = "S"
BRANDING_BADGE_MAX_LEN = 24





def _safe_get(obj, key, default=""):
    if obj is None:
        return default
    if isinstance(obj, dict):
        val = obj.get(key, default)
        return default if val is None else val
    try:
        val = getattr(obj, key, default)
        return default if val is None else val
    except Exception:
        return default

def _normalize_branding_from_row(row: models.SystemSettings | None) -> dict[str, str | bool]:
    if row is None:
        display = DEFAULT_PRODUCT_DISPLAY_NAME
        nav_raw_stored = ""
        nav_short = display
        badge = DEFAULT_BRAND_INITIAL
    else:
        display = _safe_get(row, "product_display_name", DEFAULT_PRODUCT_DISPLAY_NAME).strip() or DEFAULT_PRODUCT_DISPLAY_NAME
        nav_raw_stored = _safe_get(row, "product_nav_short", "").strip()
        nav_short = nav_raw_stored if nav_raw_stored else display
        raw_initial = _safe_get(row, "brand_initial", "").strip()
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


from .services import leave_policy

def _load_branding_into_request(request: Request) -> None:
    # 1차로 인메모리 캐시 확인 (DB 세션 생성 및 쿼리 생략)
    cache = leave_policy._SYSTEM_SETTINGS_CACHE
    if cache is not None:
        b = _normalize_branding_from_row(cache)
        request.state.product_display_name = b["product_display_name"]
        request.state.product_nav_short = b["product_nav_short"]
        request.state.product_nav_short_raw = b["product_nav_short_raw"]
        request.state.brand_nav_show_subtitle = b["brand_nav_show_subtitle"]
        request.state.brand_initial = b["brand_initial"]
        request.state.brand_badge_display = b["brand_badge_display"]
        return

    db = database.SessionLocal()
    try:
        row = leave_policy.get_system_settings(db)
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
    ctx = {
        "product_display_name": getattr(request.state, "product_display_name", DEFAULT_PRODUCT_DISPLAY_NAME),
        "product_nav_short": getattr(request.state, "product_nav_short", DEFAULT_PRODUCT_DISPLAY_NAME),
        "product_nav_short_raw": getattr(request.state, "product_nav_short_raw", ""),
        "brand_nav_show_subtitle": getattr(request.state, "brand_nav_show_subtitle", False),
        "brand_initial": getattr(request.state, "brand_initial", DEFAULT_BRAND_INITIAL),
        "brand_badge_display": getattr(request.state, "brand_badge_display", DEFAULT_BRAND_INITIAL),
        "is_default_password": getattr(request.state, "is_default_password", False),
    }

    # 관리자 페이지(/admin/*) 요청일 경우 사이드바용 실시간 시스템 현황 주입
    if request.url.path.startswith("/admin"):
        # Reuse existing DB session from request state if available to prevent connection leaks
        db = getattr(request.state, "db", None)
        db_created = False
        if db is None:
            db = database.SessionLocal()
            db_created = True
        try:
            active_users_count = db.query(models.Users).filter(
                models.Users.role != "ADMIN",
                models.Users.is_active == True
            ).count()
            pending_leaves_count = db.query(models.Leaves).filter(
                models.Leaves.status == "PENDING"
            ).count()
            
            ctx["active_users_count"] = active_users_count
            ctx["pending_leaves_count"] = pending_leaves_count
        except Exception:
            if db_created:
                db.rollback()
        finally:
            if db_created:
                db.close()

    return ctx

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
templates.env.globals["app_version"] = APP_VERSION
templates.env.globals["min"] = min
templates.env.globals["max"] = max
templates.env.globals["string_to_badge_style"] = utils.string_to_badge_style
templates.env.filters["format_datetime_kst"] = utils.format_datetime_kst
app.state.templates = templates

from .routers import api_user
from .routers.admin import page_router as admin_page_router, api_router as admin_api_router
from .dependencies import NotAuthenticatedException, PermissionDeniedException
from fastapi.responses import JSONResponse

@app.exception_handler(NotAuthenticatedException)
async def not_authenticated_exception_handler(request: Request, exc: NotAuthenticatedException):
    path = request.url.path
    if path.startswith("/static/") or path.startswith("/docs") or path == "/openapi.json" or path == "/favicon.ico":
        return Response(status_code=404)
    if path.startswith("/api/"):
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    
    cookie_settings = auth.get_cookie_settings(request)
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(
        key="access_token",
        httponly=cookie_settings.get("httponly", True),
        samesite=cookie_settings.get("samesite", "lax"),
        secure=cookie_settings.get("secure", False)
    )
    return response

@app.exception_handler(PermissionDeniedException)
async def permission_denied_exception_handler(request: Request, exc: PermissionDeniedException):
    path = request.url.path
    if path.startswith("/static/") or path.startswith("/docs") or path == "/openapi.json" or path == "/favicon.ico":
        return Response(status_code=404)
    if path.startswith("/api/"):
        return JSONResponse(status_code=403, content={"detail": "Permission denied"})
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

app.include_router(api_user.page_router)
app.include_router(api_user.api_router)
app.include_router(admin_page_router)
app.include_router(admin_api_router)

from .routers import api_notifications
app.include_router(api_notifications.router)


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
    # 1. 분산 락 동기화가 장착된 데이터베이스 초기화 및 마이그레이션 실행
    try:
        from tools.scripts.db_init import init_db
        init_db()
    except Exception as init_err:
        print(f"[SHIM CRITICAL ERROR] Database startup migration failed: {init_err}")
        sys.exit(1)

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

        # 4. 비밀키 일관성(Fail-Fast) 검증 추가
        import hashlib
        from .auth import get_encryption_key
        
        current_key = get_encryption_key()
        current_key_hash = hashlib.sha256(current_key).hexdigest() if current_key else "PLAINTEXT_MODE"
        
        settings = db.query(models.SystemSettings).first()
        if settings:
            if settings.key_hash_snapshot is None:
                # 최초 컬럼 생성에 따른 초기 값 세팅
                users_with_data = db.query(models.Users).all()
                has_encrypted_data = False
                
                for u in users_with_data:
                    raw_val = db.execute(
                        text("SELECT user_name FROM users WHERE user_id = :uid"),
                        {"uid": u.user_id}
                    ).scalar()
                    if raw_val and raw_val.startswith("gAAAAAB"):
                        has_encrypted_data = True
                        break
                
                if has_encrypted_data:
                    if current_key_hash == "PLAINTEXT_MODE":
                        print("[SHIM CRITICAL ERROR] 구동에 실패했습니다!")
                        print("기존 데이터베이스는 PII 암호화가 적용되어 있으나, 현재 비밀키 설정이 제공되지 않았습니다.")
                        print("데이터 손실 방지를 위해 기동을 즉시 차단합니다. 비밀키 설정을 복구해 주십시오.")
                        sys.exit(1)
                    else:
                        settings.key_hash_snapshot = current_key_hash
                else:
                    has_plain_data = len(users_with_data) > 0
                    if has_plain_data and current_key_hash != "PLAINTEXT_MODE":
                        print("[SHIM CRITICAL ERROR] 구동에 실패했습니다!")
                        print("기존 데이터베이스는 평문 모드로 운영 중이었으나, 현재 비밀키(암호화)가 지정되었습니다.")
                        print("평문 DB에 임의로 암호키를 지정하면 검색 기능이 오작동합니다. 키 설정을 비워주십시오.")
                        sys.exit(1)
                    else:
                        settings.key_hash_snapshot = current_key_hash
            else:
                if settings.key_hash_snapshot != current_key_hash:
                    print("[SHIM CRITICAL ERROR] 구동에 실패했습니다!")
                    if settings.key_hash_snapshot == "PLAINTEXT_MODE":
                        print("기존 데이터베이스는 평문 모드(PLAINTEXT_MODE)로 기동된 상태이나, 현재 암호키가 주입되었습니다.")
                    elif current_key_hash == "PLAINTEXT_MODE":
                        print("기존 데이터베이스는 암호화 모드로 구축되었으나, 현재 비밀키 설정이 누락되었습니다.")
                    else:
                        print("현재 설정된 암호키가 기존 데이터베이스의 암호키와 일치하지 않습니다.")
                    print("데이터 손실 방지를 위해 기동을 즉시 차단합니다. 설정을 확인해 주십시오.")
                    sys.exit(1)

        db.commit()
        
        # 5. 브랜딩 및 시스템 설정 캐시 선제 로드 (Pre-populate settings cache)
        try:
            from .services.leave_policy import get_system_settings
            get_system_settings(db, force_reload=True)
            print("[SHIM] Successfully pre-populated system settings cache on startup.")
        except Exception as cache_err:
            print(f"[SHIM WARNING] Failed to pre-populate settings cache: {cache_err}")

        # 6. 시스템 메트릭 초기화 (예외 안전망 캡슐화)
        try:
            update_system_metrics_in_db(db)
        except Exception as metrics_err:
            print(f"[SHIM WARNING] Failed to initialize system metrics on startup: {metrics_err}")
    finally:
        db.close()


@app.get("/", response_class=HTMLResponse)
def read_root(request: Request, db: Session = Depends(get_db)):
    payload = auth.get_payload_from_token(request)
    if payload:
        user_id = payload.get("sub")
        token_version = payload.get("token_version")
        if user_id:
            user = db.query(models.Users).filter(models.Users.user_id == user_id).first()
            if user and user.is_active:
                effective_token_version = token_version if token_version is not None else 0
                if user.token_version == effective_token_version:
                    user_role = getattr(user, "role", "STAFF")
                    if user_role == "ADMIN":
                        return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_302_FOUND)
                    return RedirectResponse(url="/user/dashboard", status_code=status.HTTP_302_FOUND)
    
    cookie_settings = auth.get_cookie_settings(request)
    response = templates.TemplateResponse(request=request, name="login.html")
    if request.cookies.get("access_token"):
        response.delete_cookie(
            key="access_token",
            httponly=cookie_settings.get("httponly", True),
            samesite=cookie_settings.get("samesite", "lax"),
            secure=cookie_settings.get("secure", False)
        )
    return response


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

# Reload trigger comment to refresh template cache: v3.




