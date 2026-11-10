"""请求/响应模型。"""
from datetime import datetime

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str
    password: str


class UserCreateIn(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6)
    is_admin: bool = False
    brands: list[str] = []


class UserUpdateIn(BaseModel):
    password: str | None = Field(default=None, min_length=6)
    enabled: bool | None = None
    is_admin: bool | None = None
    brands: list[str] | None = None


class UserOut(BaseModel):
    id: int
    username: str
    is_admin: bool
    enabled: bool
    brands: list[str]

    class Config:
        from_attributes = True


class StoreUpdateIn(BaseModel):
    """门店配置更新；未传的字段保持不变，显式 null/空串可清空平台 ID。"""
    store_name: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None
    mt_id: str | None = None
    elm_id: str | None = None
    jd_id: str | None = None
    region: str | None = None
    remark: str | None = None
    # 用 fields_set 区分「未传」与「传了 null」；见 router 里 model_dump(exclude_unset=True)


class QualificationJobOut(BaseModel):
    id: int
    brand: str
    store_id: str = ""  # 兼容旧字段：首个非空平台门店 ID
    mt_store_id: str = ""
    elm_store_id: str = ""
    jd_store_id: str = ""
    tg_store_id: str = ""
    operator_name: str
    credit_code: str
    legal_person: str
    address: str
    main_business_type: str
    business_scope: str
    valid_until: str
    license_no: str
    approved_at: str
    status: str
    error_message: str
    created_by: int | None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    class Config:
        from_attributes = True


class QualificationJobPatchIn(BaseModel):
    """本机 worker 回报执行结果。"""
    status: str = Field(description="success 或 failed")
    error_message: str = ""
