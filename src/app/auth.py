from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
import bcrypt
import os
from fastapi import Request, HTTPException, status
from .database import _resolve_data_dir
from .key_material import (
    INSECURE_DEFAULT_SECRET_KEY,
    read_secret_file,
    resolve_encryption_key,
)
import secrets
from functools import lru_cache

BCRYPT_MAX_PASSWORD_BYTES = 72
DUMMY_PASSWORD_HASH = "$2b$12$LQv3c1yqBWpY0wK7Hro4qee0kkcB0PJj8YwHbNiY0nAqdYz8lY4qK"


def _resolve_secret_key() -> str:
    # 1) OS environment variable has top priority
    env_key = os.getenv("SHIM_SECRET_KEY", "").strip()
    if env_key:
        if env_key == INSECURE_DEFAULT_SECRET_KEY:
            raise RuntimeError(
                "SHIM_SECRET_KEY uses a known insecure default. "
                "Set a unique secret or remove the variable to use data/secret.key."
            )
        return env_key

    # 2) Read or create secret.key in the data directory
    try:
        data_dir = _resolve_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        secret_file = data_dir / "secret.key"

        existing_key, _ = read_secret_file(secret_file)
        if existing_key:
            return existing_key

        # Generate a new random secret key (64 characters)
        new_key = secrets.token_urlsafe(48)
        secret_file.write_text(f"# AUTO-GENERATED JWT KEY - DO NOT USE FOR DB COLUMN ENCRYPTION\n{new_key}", encoding="utf-8")
        print(f"[AUTH] Generated and saved a new random secret key to {secret_file}")
        return new_key
    except Exception as e:
        raise RuntimeError(
            "Unable to load or create the JWT secret key. Set SHIM_SECRET_KEY "
            "or make the SHIM data directory writable."
        ) from e

@lru_cache(maxsize=1)
def get_encryption_key() -> bytes | None:
    return resolve_encryption_key(_resolve_data_dir())

def clear_encryption_key_cache():
    """Clear the encryption key lru_cache (useful for tests when env vars change)."""
    get_encryption_key.cache_clear()

SECRET_KEY = _resolve_secret_key()

ALGORITHM = "HS256"

def _resolve_token_expire_minutes() -> int:
    env_expire = os.getenv("SHIM_JWT_EXPIRE_MINUTES", "").strip()
    if env_expire.isdigit():
        return int(env_expire)
    return 60 * 24 # 기본값 1일

ACCESS_TOKEN_EXPIRE_MINUTES = _resolve_token_expire_minutes()

def get_cookie_settings(request: Request) -> dict:
    env_samesite = os.getenv("SHIM_COOKIE_SAMESITE", "lax").lower()
    if env_samesite not in ("lax", "strict", "none"):
        env_samesite = "lax"
        
    secure_cookie = False
    env_secure = os.getenv("SHIM_SECURE_COOKIE", "").lower() in ("true", "1", "yes")
    if env_secure:
        secure_cookie = True
    elif request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https":
        secure_cookie = True
        
    return {
        "httponly": True,
        "samesite": env_samesite,
        "secure": secure_cookie
    }

def verify_password(plain_password, hashed_password):
    password_bytes = plain_password.encode("utf-8")
    if len(password_bytes) > BCRYPT_MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))
    except ValueError:
        return False


def verify_login_password(plain_password: str, stored_password_hash: str | None) -> bool:
    """로그인용 검증: 존재하지 않는 계정도 같은 bcrypt 비용을 지불합니다."""
    password_bytes = plain_password.encode("utf-8")
    if len(password_bytes) > BCRYPT_MAX_PASSWORD_BYTES:
        return False

    candidate_hash = stored_password_hash or DUMMY_PASSWORD_HASH
    try:
        verified = bcrypt.checkpw(password_bytes, candidate_hash.encode("utf-8"))
    except ValueError:
        return False
    return bool(stored_password_hash) and verified

def get_password_hash(password):
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError("비밀번호는 UTF-8 기준 72바이트 이하여야 합니다.")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user_from_token(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        token = token.replace("Bearer ", "")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        return user_id
    except JWTError:
        return None

def get_payload_from_token(request: Request) -> Optional[dict]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        token = token.replace("Bearer ", "")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
