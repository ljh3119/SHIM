from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, declarative_base
import os
import sys
from pathlib import Path


def _resolve_data_dir() -> Path:
    # 1) 운영자가 지정한 데이터 경로가 있으면 최우선 사용
    env_dir = os.environ.get("SHIM_DATA_DIR", "").strip()
    if env_dir:
        return Path(env_dir)

    # 2) PyInstaller(포터블 EXE) 실행 시 exe 옆 data 폴더 사용
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"

    # 3) 일반 소스 실행 시 프로젝트 루트 var/data 폴더 사용
    return Path(__file__).resolve().parents[2] / "var" / "data"


DB_DIR = _resolve_data_dir()
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "shim_internal.db"

engine = create_engine(
    f"sqlite:///{DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False, "timeout": 30.0},
)


@event.listens_for(engine, "connect")
def set_sqlite_pragmas(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=FULL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.execute("PRAGMA cache_size=-64000;") # 64MB cache
    cursor.execute("PRAGMA temp_store=MEMORY;")  # Temporary tables in memory
    cursor.execute("PRAGMA mmap_size=268435456;") # Memory map file up to 256MB
    cursor.execute("PRAGMA wal_autocheckpoint=1000;")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

from fastapi import Request, HTTPException


def begin_write_transaction(db):
    """SQLite 검증과 저장을 같은 쓰기 트랜잭션 안에서 직렬화합니다."""
    connection = db.connection()
    if not connection.connection.driver_connection.in_transaction:
        db.execute(text("BEGIN IMMEDIATE"))
        db.expire_all()

def get_db(request: Request = None):
    db = SessionLocal()
    if request is not None:
        request.state.db = db
    try:
        if request is not None and request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/"):
            try:
                begin_write_transaction(db)
            except OperationalError as exc:
                db.rollback()
                if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                    raise HTTPException(status_code=503, detail="다른 요청을 처리 중입니다. 잠시 후 다시 시도해 주세요.") from exc
                raise
        yield db
    finally:
        db.close()
