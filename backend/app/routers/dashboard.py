"""看板接口。查询参数统一：brand/start/end/platforms/store_ids。"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import business_engine, get_app_db
from ..deps import authorize_brand, get_current_user
from ..models import User
from ..services import dashboard
from ..services import stores as store_svc

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _params(
    brand: str,
    start: date = Query(..., description="开始日期 YYYY-MM-DD"),
    end: date = Query(..., description="结束日期 YYYY-MM-DD"),
    platforms: str | None = Query(None, description="逗号分隔的平台"),
    store_ids: str | None = Query(None, description="逗号分隔的门店id"),
):
    return (
        brand,
        start,
        end,
        platforms.split(",") if platforms else None,
        store_ids.split(",") if store_ids else None,
    )


def _effective_stores(db: Session, brand: str, store_ids: list[str] | None) -> list[str] | None:
    """把停用门店从查询范围里剔除。"""
    return store_svc.resolve_effective_store_ids(db, brand, store_ids)


@router.get("/summary")
def summary(
    user: User = Depends(get_current_user),
    p=Depends(_params),
    db: Session = Depends(get_app_db),
):
    brand, start, end, plats, store_ids = p
    authorize_brand(user, brand)
    store_ids = _effective_stores(db, brand, store_ids)
    with business_engine.connect() as conn:
        return dashboard.summary_with_compare(conn, brand, start, end, plats, store_ids)


@router.get("/trend")
def trend(
    user: User = Depends(get_current_user),
    p=Depends(_params),
    db: Session = Depends(get_app_db),
):
    brand, start, end, plats, store_ids = p
    authorize_brand(user, brand)
    store_ids = _effective_stores(db, brand, store_ids)
    with business_engine.connect() as conn:
        return dashboard.trend(conn, brand, start, end, plats, store_ids)


@router.get("/by-platform")
def by_platform(
    user: User = Depends(get_current_user),
    p=Depends(_params),
    db: Session = Depends(get_app_db),
):
    brand, start, end, plats, store_ids = p
    authorize_brand(user, brand)
    store_ids = _effective_stores(db, brand, store_ids)
    with business_engine.connect() as conn:
        return dashboard.by_platform(conn, brand, start, end, plats, store_ids)


@router.get("/stores")
def stores(
    user: User = Depends(get_current_user),
    p=Depends(_params),
    db: Session = Depends(get_app_db),
):
    brand, start, end, plats, store_ids = p
    authorize_brand(user, brand)
    store_ids = _effective_stores(db, brand, store_ids)
    with business_engine.connect() as conn:
        return dashboard.by_store(conn, brand, start, end, plats, store_ids)


@router.get("/meal-type")
def meal_type(
    user: User = Depends(get_current_user),
    p=Depends(_params),
    db: Session = Depends(get_app_db),
):
    brand, start, end, plats, store_ids = p
    authorize_brand(user, brand)
    store_ids = _effective_stores(db, brand, store_ids)
    with business_engine.connect() as conn:
        return dashboard.meal_type(conn, brand, start, end, plats, store_ids)


@router.get("/products")
def products(
    user: User = Depends(get_current_user),
    p=Depends(_params),
    db: Session = Depends(get_app_db),
):
    brand, start, end, plats, store_ids = p
    authorize_brand(user, brand)
    store_ids = _effective_stores(db, brand, store_ids)
    with business_engine.connect() as conn:
        return dashboard.top_products(conn, brand, start, end, plats, store_ids)


@router.get("/product-trend")
def product_trend(
    name: str = Query(..., description="商品名称（精确匹配）"),
    user: User = Depends(get_current_user),
    p=Depends(_params),
    db: Session = Depends(get_app_db),
):
    brand, start, end, plats, store_ids = p
    authorize_brand(user, brand)
    store_ids = _effective_stores(db, brand, store_ids)
    with business_engine.connect() as conn:
        return dashboard.product_trend(conn, brand, start, end, plats, store_ids, name)


@router.get("/activities")
def activities(
    user: User = Depends(get_current_user),
    p=Depends(_params),
    db: Session = Depends(get_app_db),
):
    """营销活动：按分类、按门店两套汇总（仅配置了 activity 表的品牌有数据）。"""
    brand, start, end, plats, store_ids = p
    authorize_brand(user, brand)
    store_ids = _effective_stores(db, brand, store_ids)
    with business_engine.connect() as conn:
        return {
            "categories": dashboard.activity_by_category(conn, brand, start, end, plats, store_ids),
            "stores": dashboard.activity_by_store(conn, brand, start, end, plats, store_ids),
            "store_categories": dashboard.activity_by_store_category(
                conn, brand, start, end, plats, store_ids,
            ),
        }


@router.get("/abnormal-orders")
def abnormal_orders(
    user: User = Depends(get_current_user),
    p=Depends(_params),
    db: Session = Depends(get_app_db),
):
    """异常订单：按门店 × 商家服务问题计数（当前仅 xj 美团）。"""
    brand, start, end, plats, store_ids = p
    authorize_brand(user, brand)
    store_ids = _effective_stores(db, brand, store_ids)
    with business_engine.connect() as conn:
        return dashboard.abnormal_by_store(conn, brand, start, end, plats, store_ids)


@router.get("/exposure-funnel")
def exposure_funnel(
    user: User = Depends(get_current_user),
    p=Depends(_params),
    db: Session = Depends(get_app_db),
):
    """流量漏斗：曝光人数 → 入店人数 → 下单人数（多平台合并加总）。"""
    brand, start, end, plats, store_ids = p
    authorize_brand(user, brand)
    store_ids = _effective_stores(db, brand, store_ids)
    with business_engine.connect() as conn:
        return dashboard.exposure_funnel(conn, brand, start, end, plats, store_ids)


@router.get("/exposure-trend")
def exposure_trend(
    user: User = Depends(get_current_user),
    p=Depends(_params),
    db: Session = Depends(get_app_db),
):
    """流量按日趋势：各平台分开展示（忽略平台筛选），含人数与转化率。"""
    brand, start, end, _plats, store_ids = p
    authorize_brand(user, brand)
    store_ids = _effective_stores(db, brand, store_ids)
    with business_engine.connect() as conn:
        return dashboard.exposure_trend(conn, brand, start, end, None, store_ids)
