"""认证接口。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_app_db
from ..deps import get_current_user, user_brands
from ..models import LoginLog, User
from ..schemas import LoginIn
from ..security import create_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# 写入登录记录的结果说明，只给管理员看；接口对外的错误文案仍不区分「用户不存在」和「密码错误」
_LOGIN_OK = "登录成功"
_LOGIN_UNKNOWN = "用户不存在"
_LOGIN_BAD_PASSWORD = "密码错误"
_LOGIN_DISABLED = "账号已停用"


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "is_admin": user.is_admin,
        "brands": user_brands(user),
    }


def _client_ip(request: Request) -> str:
    """访客 IP。本机反代（Nginx）时读 X-Real-IP，直连时用套接字地址，避免信任客户端自报的头。"""
    peer = request.client.host if request.client else ""
    if peer in {"127.0.0.1", "::1"}:
        real = (request.headers.get("x-real-ip") or "").strip()
        if real:
            return real[:64]
    return peer[:64]


def _record_login(
    db: Session,
    *,
    username: str,
    user_id: int | None,
    success: bool,
    detail: str,
    ip: str,
) -> None:
    db.add(LoginLog(
        username=username[:50],
        user_id=user_id,
        success=success,
        detail=detail,
        ip=ip,
    ))
    db.commit()


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_app_db)):
    ip = _client_ip(request)
    user = db.query(User).filter(User.username == body.username).first()
    if user is None:
        _record_login(db, username=body.username, user_id=None, success=False, detail=_LOGIN_UNKNOWN, ip=ip)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not verify_password(body.password, user.password_hash):
        _record_login(db, username=body.username, user_id=user.id, success=False, detail=_LOGIN_BAD_PASSWORD, ip=ip)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.enabled:
        _record_login(db, username=body.username, user_id=user.id, success=False, detail=_LOGIN_DISABLED, ip=ip)
        raise HTTPException(status_code=403, detail="账号已被停用")
    _record_login(db, username=user.username, user_id=user.id, success=True, detail=_LOGIN_OK, ip=ip)
    return {"token": create_token(user.id), "user": _user_payload(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_payload(user)
