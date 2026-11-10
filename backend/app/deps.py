"""FastAPI 依赖：登录态、管理员、品牌授权校验。"""
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .database import get_app_db
from .config import BRANDS
from .models import User
from .security import decode_token
from sqlalchemy.orm import Session

# 注册到 OpenAPI，让 /docs 出现右上角 Authorize 按钮
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_app_db),
) -> User:
    token = credentials.credentials if credentials else ""
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    user_id = decode_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="登录已过期")
    user = db.get(User, user_id)
    if user is None or not user.enabled:
        raise HTTPException(status_code=401, detail="账号不可用")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def user_brands(user: User) -> list[str]:
    # 管理员天然可见全部品牌
    if user.is_admin:
        return list(BRANDS)
    return [ub.brand for ub in user.brands]


def authorize_brand(user: User, brand: str) -> None:
    if brand not in user_brands(user):
        raise HTTPException(status_code=403, detail="无权访问该品牌数据")
