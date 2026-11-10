"""品牌门店配置：名单来自 Excel「门店名称」导入；销售表仅补空平台 ID。"""
from sqlalchemy import func, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from .. import config
from ..models import BrandStore
from .dashboard import _sales

# 业务「平台」列取值 -> BrandStore 字段
_PLATFORM_ID_FIELD = {
    "美团": "mt_id",
    "饿了么": "elm_id",
    "京东": "jd_id",
}

# 空结果时用不可能命中的占位 id，避免 store_ids=[] 被当成「不过滤」
_EMPTY_MATCH = ["__no_enabled_store__"]


def _sid(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def discover_platform_ids_from_sales(conn: Connection, brand: str) -> dict[str, dict]:
    """从销售表按门店名称汇总各平台门店 ID（仅作 info 的补充）。"""
    t, m = _sales(brand)
    stmt = select(
        m["store_name"].label("store_name"),
        m["platform"].label("platform"),
        m["store_id"].label("store_id"),
    ).distinct()
    by_name: dict[str, dict] = {}
    for r in conn.execute(stmt).mappings():
        name = (r["store_name"] or "").strip()
        if not name:
            continue
        row = by_name.setdefault(name, {"mt_id": None, "elm_id": None, "jd_id": None})
        field = _PLATFORM_ID_FIELD.get(r["platform"] or "")
        sid = _sid(r["store_id"])
        if field and sid:
            row[field] = sid
    return by_name


def discover_from_sales_fallback(conn: Connection, brand: str) -> dict[str, dict]:
    """无可用 info 门店时的兜底：从销售表发现门店（含区域）。"""
    t, m = _sales(brand)
    cols = [
        m["store_name"].label("store_name"),
        m["platform"].label("platform"),
        m["store_id"].label("store_id"),
    ]
    has_region = "region" in m
    if has_region:
        cols.append(m["region"].label("region"))
    stmt = select(*cols).distinct()
    by_name: dict[str, dict] = {}
    for r in conn.execute(stmt).mappings():
        name = (r["store_name"] or "").strip()
        if not name:
            continue
        row = by_name.setdefault(
            name, {"mt_id": None, "elm_id": None, "jd_id": None, "region": None}
        )
        field = _PLATFORM_ID_FIELD.get(r["platform"] or "")
        sid = _sid(r["store_id"])
        if field and sid:
            row[field] = sid
        if has_region and r.get("region") and not row["region"]:
            row["region"] = r["region"]
    return by_name


def sync_brand_stores(app_db: Session, conn: Connection, brand: str) -> int:
    """同步门店配置到程序库。

    门店名单以 Excel「门店名称」导入的 brand_stores 为准，本函数不再增删行、不改区域。
    - 已有配置：仅用销售表补空的平台 ID（mt/elm/jd）
    - 尚无任何配置：从销售表发现门店做首次填充（兼容空库）
    """
    if brand not in config.BRANDS:
        return 0

    existing_list = (
        app_db.query(BrandStore).filter(BrandStore.brand == brand).all()
    )
    sales_ids = discover_platform_ids_from_sales(conn, brand)

    # 已有门店名单（Excel 导入）：只补空平台 ID，不动名称/区域/启停
    if existing_list:
        for cur in existing_list:
            sid = sales_ids.get(cur.store_name) or {}
            if not cur.mt_id and sid.get("mt_id"):
                cur.mt_id = sid["mt_id"]
            if not cur.elm_id and sid.get("elm_id"):
                cur.elm_id = sid["elm_id"]
            if not cur.jd_id and sid.get("jd_id"):
                cur.jd_id = sid["jd_id"]
        app_db.commit()
        return 0

    # 空库兜底：从销售表发现
    discovered = discover_from_sales_fallback(conn, brand)
    added = 0
    for name, info in discovered.items():
        app_db.add(
            BrandStore(
                brand=brand,
                store_name=name,
                enabled=True,
                mt_id=info["mt_id"],
                elm_id=info["elm_id"],
                jd_id=info["jd_id"],
                region=info["region"],
            )
        )
        added += 1
    app_db.commit()
    return added


def store_out(s: BrandStore) -> dict:
    return {
        "id": s.id,
        "brand": s.brand,
        "store_name": s.store_name,
        "enabled": s.enabled,
        "mt_id": s.mt_id,
        "elm_id": s.elm_id,
        "jd_id": s.jd_id,
        "region": s.region,
        "remark": s.remark,
    }


def list_stores(app_db: Session, brand: str) -> list[dict]:
    rows = (
        app_db.query(BrandStore)
        .filter(BrandStore.brand == brand)
        .order_by(BrandStore.enabled.desc(), BrandStore.store_name)
        .all()
    )
    return [store_out(s) for s in rows]


def get_store(app_db: Session, store_id: int) -> BrandStore | None:
    return app_db.get(BrandStore, store_id)


def _clean(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def update_store(
    app_db: Session,
    store: BrandStore,
    *,
    store_name: str | None = None,
    enabled: bool | None = None,
    mt_id=...,
    elm_id=...,
    jd_id=...,
    region=...,
    remark=...,
) -> BrandStore:
    if store_name is not None:
        name = store_name.strip()
        if not name:
            raise ValueError("门店名称不能为空")
        clash = (
            app_db.query(BrandStore)
            .filter(
                BrandStore.brand == store.brand,
                BrandStore.store_name == name,
                BrandStore.id != store.id,
            )
            .first()
        )
        if clash:
            raise ValueError("同品牌下已存在同名门店")
        store.store_name = name
    if enabled is not None:
        store.enabled = enabled
    # Ellipsis 表示未传；None / 空串表示清空
    if mt_id is not ...:
        store.mt_id = _clean(mt_id)
    if elm_id is not ...:
        store.elm_id = _clean(elm_id)
    if jd_id is not ...:
        store.jd_id = _clean(jd_id)
    if region is not ...:
        store.region = _clean(region)
    if remark is not ...:
        store.remark = _clean(remark)
    app_db.commit()
    app_db.refresh(store)
    return store


def _platform_ids(store: BrandStore) -> list[str]:
    return [x for x in (store.mt_id, store.elm_id, store.jd_id) if x]


def disabled_store_names(app_db: Session, brand: str) -> set[str]:
    rows = (
        app_db.query(BrandStore.store_name)
        .filter(BrandStore.brand == brand, BrandStore.enabled.is_(False))
        .all()
    )
    return {r[0] for r in rows}


def resolve_effective_store_ids(
    app_db: Session, brand: str, store_ids: list[str] | None
) -> list[str] | None:
    """结合启停状态解析查询用的门店 id。

    - 未配置任何 brand_stores：不额外过滤（兼容未同步）
    - 有配置且未选手动门店：若存在停用则限制为已启用门店的平台 id
    - 有手动选择：去掉已停用门店的平台 id
    """
    total = app_db.query(func.count(BrandStore.id)).filter(BrandStore.brand == brand).scalar() or 0
    if total == 0:
        return store_ids

    disabled = (
        app_db.query(BrandStore)
        .filter(BrandStore.brand == brand, BrandStore.enabled.is_(False))
        .all()
    )
    disabled_ids = {sid for s in disabled for sid in _platform_ids(s)}

    if store_ids:
        filtered = [x for x in store_ids if x not in disabled_ids]
        return filtered or _EMPTY_MATCH

    enabled = (
        app_db.query(BrandStore)
        .filter(BrandStore.brand == brand, BrandStore.enabled.is_(True))
        .all()
    )
    ids = [sid for s in enabled for sid in _platform_ids(s)]
    # 有停用门店时必须显式限制；全启用可不加过滤
    if not disabled_ids:
        return None
    return ids or _EMPTY_MATCH
