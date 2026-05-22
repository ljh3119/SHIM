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
    user_id = auth.get_current_user_from_token(request)
    if not user_id:
        raise NotAuthenticatedException()
    user = db.query(models.Users).filter(models.Users.user_id == user_id).first()
    if not user or not user.is_active:
        raise NotAuthenticatedException()
    return user

def get_current_admin(current_user: models.Users = Depends(get_current_user)) -> models.Users:
    user_role = getattr(current_user, "role", "")
    is_admin = getattr(current_user, "is_admin", False)
    if user_role != "ADMIN" and not is_admin:
        raise PermissionDeniedException()
    return current_user
