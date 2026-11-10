"""品牌门店配置：列表、同步、启停与改 ID（仅管理员）。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import business_engine, get_app_db
from ..deps import require_admin
from ..models import User
from ..schemas import StoreUpdateIn
from ..services import stores as store_svc

router = APIRouter(
    prefix="/stores",
    tags=["stores"],
    dependencies=[Depends(require_admin)],
)


@router.get("")
def list_stores(
    brand: str = Query(..., description="品牌简写"),
    sync: bool = Query(True, description="是否先从业务库同步新门店"),
    user: User = Depends(require_admin),
    db: Session = Depends(get_app_db),
):
    if sync:
        with business_engine.connect() as conn:
            store_svc.sync_brand_stores(db, conn, brand)
    return store_svc.list_stores(db, brand)


@router.post("/sync")
def sync_stores(
    brand: str = Query(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_app_db),
):
    """补全空缺平台 ID；名单为空时才从销售表发现门店。"""
    with business_engine.connect() as conn:
        added = store_svc.sync_brand_stores(db, conn, brand)
    return {"ok": True, "added": added, "stores": store_svc.list_stores(db, brand)}


@router.put("/{store_id}")
def update_store(
    store_id: int,
    body: StoreUpdateIn,
    user: User = Depends(require_admin),
    db: Session = Depends(get_app_db),
):
    store = store_svc.get_store(db, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="门店不存在")
    data = body.model_dump(exclude_unset=True)
    kwargs = {}
    if "store_name" in data:
        kwargs["store_name"] = data["store_name"]
    if "enabled" in data:
        kwargs["enabled"] = data["enabled"]
    for key in ("mt_id", "elm_id", "jd_id", "region", "remark"):
        if key in data:
            kwargs[key] = data[key]
    try:
        store = store_svc.update_store(db, store, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return store_svc.store_out(store)
