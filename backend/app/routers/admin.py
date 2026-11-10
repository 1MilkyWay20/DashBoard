"""管理端：用户 CRUD 与品牌授权。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import BRANDS
from ..database import get_app_db
from ..deps import require_admin
from ..models import LoginLog, User, UserBrand
from ..schemas import UserCreateIn, UserUpdateIn
from ..security import hash_password

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

# 登录记录分页：默认 20 条，单页最多 100，避免一次拉全表
LOGIN_LOG_PAGE_SIZE = 20
LOGIN_LOG_PAGE_SIZE_MAX = 100


@router.get("/brands")
def brand_list():
    """可分配的品牌清单（来自 config.BRANDS）。"""
    return [{"key": k, "label": v["label"]} for k, v in BRANDS.items()]


def _user_out(user: User) -> dict:
    """手工组装，避免 ORM 关系对象直接进响应模型。"""
    return {
        "id": user.id,
        "username": user.username,
        "is_admin": user.is_admin,
        "enabled": user.enabled,
        "brands": [ub.brand for ub in user.brands],
    }


@router.get("/users")
def user_list(db: Session = Depends(get_app_db)):
    return [_user_out(u) for u in db.query(User).order_by(User.id).all()]


@router.post("/users")
def create_user(body: UserCreateIn, db: Session = Depends(get_app_db)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    unknown = set(body.brands) - set(BRANDS)
    if unknown:
        raise HTTPException(status_code=400, detail=f"未知品牌: {', '.join(unknown)}")
    user = User(username=body.username, password_hash=hash_password(body.password),
                is_admin=body.is_admin)
    user.brands = [UserBrand(brand=b) for b in body.brands]
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.put("/users/{user_id}")
def update_user(user_id: int, body: UserUpdateIn, db: Session = Depends(get_app_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if body.password:
        user.password_hash = hash_password(body.password)
    if body.enabled is not None:
        user.enabled = body.enabled
    if body.is_admin is not None:
        user.is_admin = body.is_admin
    if body.brands is not None:
        unknown = set(body.brands) - set(BRANDS)
        if unknown:
            raise HTTPException(status_code=400, detail=f"未知品牌: {', '.join(unknown)}")
        # 先清空再写入：直接赋值时 SQLAlchemy 可能先 INSERT 后 DELETE，
        # 撞上 (user_id, brand) 唯一约束导致整次保存（含改密）失败
        user.brands.clear()
        db.flush()
        user.brands = [UserBrand(brand=b) for b in body.brands]
    db.commit()
    db.refresh(user)
    return _user_out(user)


def _login_log_out(row: LoginLog) -> dict:
    created = row.created_at.strftime("%Y-%m-%d %H:%M:%S") if row.created_at else ""
    return {
        "id": row.id,
        "username": row.username,
        "success": row.success,
        "detail": row.detail,
        "ip": row.ip,
        "created_at": created,
    }


@router.get("/login-logs")
def login_log_list(
    page: int = 1,
    page_size: int = LOGIN_LOG_PAGE_SIZE,
    username: str = "",
    success: bool | None = None,
    db: Session = Depends(get_app_db),
):
    """登录记录，新的在前。username 为包含匹配，success 不传则成功失败都返回。"""
    page = max(page, 1)
    page_size = min(max(page_size, 1), LOGIN_LOG_PAGE_SIZE_MAX)
    query = db.query(LoginLog)
    keyword = username.strip()
    if keyword:
        query = query.filter(LoginLog.username.contains(keyword, autoescape=True))
    if success is not None:
        query = query.filter(LoginLog.success.is_(success))
    total = query.with_entities(func.count(LoginLog.id)).scalar() or 0
    rows = (
        query.order_by(LoginLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_login_log_out(row) for row in rows],
    }


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_app_db), admin: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    db.delete(user)
    db.commit()
    return {"ok": True}
