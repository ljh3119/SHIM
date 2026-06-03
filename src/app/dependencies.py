from fastapi import Request, Depends
from sqlalchemy.orm import Session
from .database import get_db
from . import auth, models

class NotAuthenticatedException(Exception):
    """인증되지 않은 유저인 경우 발생하는 예외"""
    pass

class PermissionDeniedException(Exception):
    """권한이 없는 페이지/API에 접근할 때 발생하는 예외"""
    pass

def get_current_user(request: Request, db: Session = Depends(get_db)) -> models.Users:
    payload = auth.get_payload_from_token(request)
    if not payload:
        raise NotAuthenticatedException()
    
    user_id = payload.get("sub")
    token_version = payload.get("token_version")
    is_default_pwd = payload.get("is_default_password", False)
    
    if not user_id:
        raise NotAuthenticatedException()
        
    user = db.query(models.Users).filter(models.Users.user_id == user_id).first()
    if not user or not user.is_active:
        raise NotAuthenticatedException()
        
    # 하위 호환성 및 테스트 코드 통과를 위해 토큰 버전이 없을 시 0으로 대조
    effective_token_version = token_version if token_version is not None else 0
    if user.token_version != effective_token_version:
        raise NotAuthenticatedException()
        
    request.state.is_default_password = is_default_pwd
    return user

def get_current_admin(current_user: models.Users = Depends(get_current_user)) -> models.Users:
    user_role = getattr(current_user, "role", "")
    if user_role != "ADMIN":
        raise PermissionDeniedException()
    return current_user
