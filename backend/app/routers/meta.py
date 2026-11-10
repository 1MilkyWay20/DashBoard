"""筛选器元数据：平台、门店下拉选项。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import config
from ..database import business_engine, get_app_db
from ..deps import authorize_brand, get_current_user, user_brands
from ..models import User
from ..services import dashboard
from ..services import stores as store_svc

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/brands")
def visible_brands(user: User = Depends(get_current_user)):
    """当前用户可见的品牌（key + 显示名），供侧边栏菜单。"""
    keys = user_brands(user)
    return [{"key": k, "label": config.BRANDS[k]["label"]} for k in keys if k in config.BRANDS]


@router.get("/brands/summary")
def visible_brands_summary(user: User = Depends(get_current_user)):
    """可见品牌 + 各自最近一天的概览指标，用于品牌选择页卡片。

    可见范围同样来自 user_brands 过滤（即品牌授权强校验）；
    单个品牌查询失败不影响整体，该品牌 stats 为 null，前端显示"--"。
    """
    keys = [k for k in user_brands(user) if k in config.BRANDS]
    out = []
    with business_engine.connect() as conn:
        for k in keys:
            stats = None
            try:
                stats = dashboard.latest_day_summary(conn, k)
            except Exception:  # 该品牌销售表异常时按无数据处理
                pass
            out.append({"key": k, "label": config.BRANDS[k]["label"], "stats": stats})
    return out


@router.get("/platforms")
def platforms(brand: str, user: User = Depends(get_current_user)):
    authorize_brand(user, brand)
    with business_engine.connect() as conn:
        return dashboard.meta_platforms(conn, brand)


@router.get("/stores")
def stores(
    brand: str,
    platform: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_app_db),
):
    """门店树：{ tree, node_stores }，含完整机构父级，选父级可汇总下属门店。

    停用门店不出现在筛选树中；首次访问时顺带补全空缺平台 ID。
    """
    authorize_brand(user, brand)
    with business_engine.connect() as conn:
        store_svc.sync_brand_stores(db, conn, brand)
        data = dashboard.meta_stores(conn, brand, platform)
    disabled = store_svc.disabled_store_names(db, brand)
    if not disabled:
        return data
    # 从树与 node_stores 中剔除停用门店（叶子 value 为 s:门店名）
    def prune(nodes: list[dict]) -> list[dict]:
        out = []
        for n in nodes:
            val = n.get("value", "")
            if val.startswith("s:"):
                name = val[2:]
                if name in disabled:
                    continue
                out.append(n)
                continue
            children = prune(n.get("children") or [])
            if not children and n.get("children") is not None:
                continue  # 父级下已无可用门店则去掉
            node = {**n}
            if children:
                node["children"] = children
            elif "children" in node:
                del node["children"]
            out.append(node)
        return out

    tree = prune(data.get("tree") or [])
    node_stores = {
        k: v
        for k, v in (data.get("node_stores") or {}).items()
        if not (k.startswith("s:") and k[2:] in disabled)
    }
    # 父级 node_stores 仍可能含停用门店 id；按启用门店 id 再滤一遍
    enabled_ids = set()
    for k, ids in list(node_stores.items()):
        if k.startswith("s:"):
            enabled_ids.update(ids)
    for k, ids in list(node_stores.items()):
        if not k.startswith("s:"):
            node_stores[k] = [i for i in ids if i in enabled_ids]
    return {"tree": tree, "node_stores": node_stores}
