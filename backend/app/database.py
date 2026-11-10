"""两个数据库连接：业务库（只读查询）和程序库（用户/授权表）。"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import APP_DB_URL, DATABASE_URL

"""业务库引擎。"""
business_engine = create_engine(DATABASE_URL, pool_pre_ping=True)
"""程序库引擎。"""
app_engine = create_engine(APP_DB_URL, pool_pre_ping=True)

"""业务库会话。"""
BusinessSession = sessionmaker(bind=business_engine)
"""程序库会话。"""
AppSession = sessionmaker(bind=app_engine)


class AppBase(DeclarativeBase):
    """程序库的表基类。"""


def get_app_db():
    db = AppSession()
    try:
        yield db
    finally:
        db.close()


def get_business_db():
    db = BusinessSession()
    try:
        yield db
    finally:
        db.close()
