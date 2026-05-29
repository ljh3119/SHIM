from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
import bcrypt
import os
from fastapi import Request, HTTPException, status
from .database import _resolve_data_dir
import secrets

def _resolve_secret_key() -> str:
    # 1) OS environment variable has top priority
    env_key = os.getenv("SHIM_SECRET_KEY", "").strip()
    if env_key:
        return env_key

    # 2) Read or create secret.key in the data directory
    try:
        data_dir = _resolve_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        secret_file = data_dir / "secret.key"

        if secret_file.exists():
            return secret_file.read_text(encoding="utf-8").strip()

        # Generate a new random secret key (64 characters)
        new_key = secrets.token_urlsafe(48)
        secret_file.write_text(new_key, encoding="utf-8")
        print(f"[AUTH] Generated and saved a new random secret key to {secret_file}")
        return new_key
    except Exception as e:
        print(f"[AUTH] Error resolving or writing secret.key: {e}")
        return "shim_change_this_secret_key_before_operation"

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
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

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
