"""程序库数据表：用户、用户-品牌授权、品牌门店配置、资质更换任务。"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import AppBase


class User(AppBase):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    brands: Mapped[list["UserBrand"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserBrand(AppBase):
    __tablename__ = "user_brands"
    __table_args__ = (UniqueConstraint("user_id", "brand", name="uq_user_brand"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    brand: Mapped[str] = mapped_column(String(50))

    user: Mapped[User] = relationship(back_populates="brands")


class BrandStore(AppBase):
    """品牌门店配置（程序库）。

    业务库只读；门店启停、平台门店 ID 等可编辑信息落在这里。
    按 brand + store_name 唯一；名单来自 Excel「门店名称」导入，
    平台 ID 可手工改，空缺时由销售表补全。
    """
    __tablename__ = "brand_stores"
    __table_args__ = (UniqueConstraint("brand", "store_name", name="uq_brand_store_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand: Mapped[str] = mapped_column(String(50), index=True)
    store_name: Mapped[str] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    mt_id: Mapped[str | None] = mapped_column(String(64), nullable=True)   # 美团门店 ID
    elm_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 饿了么门店 ID
    jd_id: Mapped[str | None] = mapped_column(String(64), nullable=True)   # 京东门店 ID
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 城市/战区/大区
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class LoginLog(AppBase):
    """登录记录。成功和失败都记，供管理员查看是谁、从哪个 IP 登进来的。

    user_id 不设外键：用户被删后记录仍保留，用户名用当时提交的字符串。
    """

    __tablename__ = "login_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    detail: Mapped[str] = mapped_column(String(50), default="")  # 登录成功 / 密码错误 等
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


class QualificationJob(AppBase):
    """资质更换任务。网页提交后 pending，本机 worker claim 后跑 Playwright。"""

    __tablename__ = "qualification_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand: Mapped[str] = mapped_column(String(50), default="xj", index=True)
    # 兼容旧列：取第一个非空平台门店 ID，作展示/证件文件名
    store_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    # 各平台门店 ID（空则 worker 跳过该平台）
    mt_store_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    elm_store_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    jd_store_id: Mapped[str] = mapped_column(String(64), default="")
    tg_store_id: Mapped[str] = mapped_column(String(64), default="")
    operator_name: Mapped[str] = mapped_column(String(200), default="")
    credit_code: Mapped[str] = mapped_column(String(64), default="")
    legal_person: Mapped[str] = mapped_column(String(100), default="")
    address: Mapped[str] = mapped_column(String(500), default="")
    main_business_type: Mapped[str] = mapped_column(String(200), default="")
    business_scope: Mapped[str] = mapped_column(String(1000), default="")
    valid_until: Mapped[str] = mapped_column(String(32), default="")  # YYYY-MM-DD
    license_no: Mapped[str] = mapped_column(String(100), default="")
    approved_at: Mapped[str] = mapped_column(String(32), default="")  # YYYY-MM-DD
    license_path: Mapped[str] = mapped_column(String(500), default="")
    # pending -> running -> success | failed
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
