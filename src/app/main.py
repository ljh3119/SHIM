from fastapi import FastAPI, Depends, Request, Form, status
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

from . import models, database, auth
from .database import engine, get_db

app = FastAPI(title="SHIM", version="1.2.1")

DEFAULT_PRODUCT_DISPLAY_NAME = "SHIM"
DEFAULT_BRAND_INITIAL = "쉼"
BRANDING_BADGE_MAX_LEN = 24


def ensure_sqlite_system_schema(db: Session) -> None:
    """Ensure SQLite schema has required columns for current app."""
    user_columns = [row[1] for row in db.execute(text("PRAGMA table_info(users)")).fetchall()]
    if "company" not in user_columns:
        db.execute(text("ALTER TABLE users ADD COLUMN company VARCHAR"))
    if "team" not in user_columns:
        db.execute(text("ALTER TABLE users ADD COLUMN team VARCHAR"))
    setting_columns = [row[1] for row in db.execute(text("PRAGMA table_info(system_settings)")).fetchall()]
    if "time_granularity_minutes" not in setting_columns:
        db.execute(text("ALTER TABLE system_settings ADD COLUMN time_granularity_minutes INTEGER DEFAULT 60"))
    if "work_start_minute" not in setting_columns:
        db.execute(text("ALTER TABLE system_settings ADD COLUMN work_start_minute INTEGER DEFAULT 540"))
    if "work_end_minute" not in setting_columns:
        db.execute(text("ALTER TABLE system_settings ADD COLUMN work_end_minute INTEGER DEFAULT 1080"))
    if "lunch_start_minute" not in setting_columns:
        db.execute(text("ALTER TABLE system_settings ADD COLUMN lunch_start_minute INTEGER"))
    if "lunch_end_minute" not in setting_columns:
        db.execute(text("ALTER TABLE system_settings ADD COLUMN lunch_end_minute INTEGER"))
    if "product_display_name" not in setting_columns:
        db.execute(text("ALTER TABLE system_settings ADD COLUMN product_display_name VARCHAR(120)"))
    if "product_nav_short" not in setting_columns:
        db.execute(text("ALTER TABLE system_settings ADD COLUMN product_nav_short VARCHAR(80)"))
    if "brand_initial" not in setting_columns:
        db.execute(text("ALTER TABLE system_settings ADD COLUMN brand_initial VARCHAR(32)"))
    db.execute(
        text(
            """
            UPDATE system_settings SET
                product_display_name = COALESCE(NULLIF(TRIM(product_display_name), ''), 'SHIM'),
                product_nav_short = TRIM(COALESCE(product_nav_short, '')),
                brand_initial = CASE
                    WHEN brand_initial IS NULL OR TRIM(brand_initial) = '' THEN 'S'
                    ELSE TRIM(brand_initial)
                END
            WHERE id IS NOT NULL
            """
        )
    )
    setting_cols_after = [row[1] for row in db.execute(text("PRAGMA table_info(system_settings)")).fetchall()]
    if "product_user_sidebar_title" in setting_cols_after:
        try:
            db.execute(text("ALTER TABLE system_settings DROP COLUMN product_user_sidebar_title"))
        except Exception:
            pass


models.Base.metadata.create_all(bind=engine)
_boot_db = database.SessionLocal()
try:
    ensure_sqlite_system_schema(_boot_db)
    _boot_db.commit()
except Exception:
    _boot_db.rollback()
    raise
finally:
    _boot_db.close()


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


def _load_branding_into_request(request: Request) -> None:
    db = database.SessionLocal()
    try:
        row = db.query(models.SystemSettings).first()
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
templates.env.globals["app_version"] = "1.2.1"
app.state.templates = templates

from .routers import api_user, api_admin
app.include_router(api_user.router)
app.include_router(api_admin.router)


@app.middleware("http")
async def branding_middleware(request: Request, call_next):
    p = request.url.path
    if p.startswith("/static") or p == "/favicon.ico":
        return await call_next(request)
    _load_branding_into_request(request)
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


def migrate_legacy_leaves_to_snapshot(db: Session):
    leave_columns = [row[1] for row in db.execute(text("PRAGMA table_info(leaves)")).fetchall()]
    if "snapshot_slot_label" not in leave_columns:
        db.execute(text("ALTER TABLE leaves ADD COLUMN snapshot_slot_label VARCHAR"))
    if "snapshot_start_min" not in leave_columns:
        db.execute(text("ALTER TABLE leaves ADD COLUMN snapshot_start_min INTEGER"))
    if "snapshot_end_min" not in leave_columns:
        db.execute(text("ALTER TABLE leaves ADD COLUMN snapshot_end_min INTEGER"))
    if "snapshot_deduction_hours" not in leave_columns:
        db.execute(text("ALTER TABLE leaves ADD COLUMN snapshot_deduction_hours FLOAT"))
    if "status" not in leave_columns:
        db.execute(text("ALTER TABLE leaves ADD COLUMN status VARCHAR DEFAULT 'APPROVED'"))
    if "rejection_reason" not in leave_columns:
        db.execute(text("ALTER TABLE leaves ADD COLUMN rejection_reason VARCHAR(500)"))

    # Fresh v1 schema may not have legacy slot_id at all.
    if "slot_id" not in leave_columns:
        db.execute(
            text(
                """
                UPDATE leaves
                SET status = COALESCE(status, 'APPROVED')
                WHERE status IS NULL
                """
            )
        )
        return

    legacy_rows = db.execute(
        text(
            """
            SELECT l.id, l.slot_id
            FROM leaves l
            WHERE l.snapshot_slot_label IS NULL
            """
        )
    ).fetchall()

    for leave_id, slot_id in legacy_rows:
        db.execute(
            text(
                """
                UPDATE leaves
                SET snapshot_slot_label = :label,
                    snapshot_start_min = :start_min,
                    snapshot_end_min = :end_min,
                    snapshot_deduction_hours = :deduction,
                    status = COALESCE(status, 'APPROVED')
                WHERE id = :leave_id
                """
            ),
            {
                "leave_id": leave_id,
                "label": f"LEGACY_SLOT_{slot_id}",
                "start_min": 0,
                "end_min": 0,
                "deduction": 0.0,
            },
        )


def ensure_operational_indexes(db: Session):
    for index_sql in [
        "CREATE INDEX IF NOT EXISTS ix_leaves_user_id_date ON leaves (user_id, date)",
        "CREATE INDEX IF NOT EXISTS ix_leaves_year_date ON leaves (year, date)",
        "CREATE INDEX IF NOT EXISTS ix_leaves_year_user_id ON leaves (year, user_id)",
        "CREATE INDEX IF NOT EXISTS ix_leaves_created_at ON leaves (created_at)",
    ]:
        db.execute(text(index_sql))


@app.on_event("startup")
def startup_event():
    db = database.SessionLocal()
    ensure_sqlite_system_schema(db)
    migrate_legacy_leaves_to_snapshot(db)
    ensure_operational_indexes(db)

    admin = db.query(models.Users).filter(models.Users.user_id == "admin").first()
    if not admin:
        hashed_pw = auth.get_password_hash("0000")
        new_admin = models.Users(user_id="admin", user_name="\uc2dc\uc2a4\ud15c\uad00\ub9ac\uc790", password=hashed_pw, is_admin=True)
        db.add(new_admin)
        db.commit()
        admin = new_admin
    elif not admin.user_name or "?" in admin.user_name:
        admin.user_name = "\uc2dc\uc2a4\ud15c\uad00\ub9ac\uc790"
    
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
            )
        )
    else:
        db.execute(
            text(
                """
                UPDATE system_settings
                SET time_granularity_minutes = COALESCE(time_granularity_minutes, 60),
                    work_start_minute = COALESCE(work_start_minute, 540),
                    work_end_minute = COALESCE(work_end_minute, 1080)
                """
            )
        )

    seed_korean_holidays(db=db, actor_id=admin.user_id, start_year=2020, end_year=2050)

    db.commit()
    db.close()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    user_id = auth.get_current_user_from_token(request)
    if user_id:
        user = db.query(models.Users).filter(models.Users.user_id == user_id).first()
        if user:
            if user.is_admin:
                return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_302_FOUND)
            return RedirectResponse(url="/user/dashboard", status_code=status.HTTP_302_FOUND)
    
    return templates.TemplateResponse(request=request, name="login.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.post("/login")
async def login(
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
        data={"sub": user.user_id}, expires_delta=access_token_expires
    )
    
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response

