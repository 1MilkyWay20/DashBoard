"""FastAPI 入口。首次启动自动建程序库表并初始化管理员。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import BRANDS, JWT_SECRET
from .database import AppBase, app_engine, get_app_db
from .models import User
from .routers import admin, ai, auth, dashboard, meta, qualification, stores
from .security import hash_password


def _ensure_qualification_store_id_columns():
    """已有 qualification_jobs 表补齐分平台门店 ID 列（create_all 不会 ALTER）。"""
    from sqlalchemy import inspect, text

    inspector = inspect(app_engine)
    if "qualification_jobs" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("qualification_jobs")}
    # 方言差异：SQLite / MySQL 都支持简单 ADD COLUMN
    adds = [
        ("mt_store_id", "VARCHAR(64) NOT NULL DEFAULT ''"),
        ("elm_store_id", "VARCHAR(64) NOT NULL DEFAULT ''"),
        ("jd_store_id", "VARCHAR(64) NOT NULL DEFAULT ''"),
        ("tg_store_id", "VARCHAR(64) NOT NULL DEFAULT ''"),
    ]
    with app_engine.begin() as conn:
        for name, ddl in adds:
            if name in existing:
                continue
            conn.execute(text(f"ALTER TABLE qualification_jobs ADD COLUMN {name} {ddl}"))
            print(f"已为 qualification_jobs 增加列 {name}")
        # 旧版单列 store_id → 回填到美团（历史 pending 任务可继续跑）
        if "store_id" in existing:
            conn.execute(
                text(
                    "UPDATE qualification_jobs SET mt_store_id = store_id "
                    "WHERE (mt_store_id IS NULL OR mt_store_id = '') "
                    "AND store_id IS NOT NULL AND store_id != ''"
                )
            )


def _init_app_db():
    """建表；无任何用户时创建初始管理员 admin / admin123。"""
    AppBase.metadata.create_all(app_engine)
    _ensure_qualification_store_id_columns()
    from sqlalchemy.orm import Session

    with Session(app_engine) as db:
        if db.query(User).count() == 0:
            db.add(User(username="admin", password_hash=hash_password("admin123"), is_admin=True))
            db.commit()
            print("已创建初始管理员：admin / admin123（生产环境请立即修改密码）")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_app_db()
    yield


app = FastAPI(title="数据可视化看板", lifespan=lifespan)

# 生产走 Nginx 同源反代，不需要 CORS；开发时前端 5173 直连后端
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(meta.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(stores.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(qualification.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True, "brands": list(BRANDS)}

