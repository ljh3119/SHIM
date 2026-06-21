from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime

from src.app import models, utils
from src.app.database import get_db
from src.app.dependencies import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

@router.get("")
def get_unread_notifications(
    db: Session = Depends(get_db),
    user: models.Users = Depends(get_current_user)
):
    # 읽지 않은 알림을 최신순으로 가져옴 (최대 30개 제한)
    unread = db.query(models.Notifications).filter(
        models.Notifications.user_id == user.user_id,
        models.Notifications.is_read == False
    ).order_by(models.Notifications.id.desc()).limit(30).all()

    res = []
    for n in unread:
        res.append({
            "id": n.id,
            "sender_id": n.sender_id,
            "message": n.message,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None
        })
    return JSONResponse(content=res)

@router.post("/{notification_id}/read")
def mark_notification_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: models.Users = Depends(get_current_user)
):
    n = db.query(models.Notifications).filter(
        models.Notifications.id == notification_id,
        models.Notifications.user_id == user.user_id
    ).first()
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    n.is_read = True
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database write failure")
    
    return JSONResponse(content={"status": "success"})

@router.post("/read-all")
def mark_all_notifications_as_read(
    db: Session = Depends(get_db),
    user: models.Users = Depends(get_current_user)
):
    try:
        db.query(models.Notifications).filter(
            models.Notifications.user_id == user.user_id,
            models.Notifications.is_read == False
        ).update({"is_read": True}, synchronize_session=False)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database write failure")
    
    return JSONResponse(content={"status": "success"})
