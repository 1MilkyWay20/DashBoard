"""从 DataProcess 2/data/*门店表.xlsx「门店名称」导入 brand_stores（替换本地 app.db）。

用法：
  cd backend && ../DataProcess\\ 2/.venv/bin/python import_stores_from_excel.py

重名合并：保留首次出现的饿了么 ID，冲突写入 remark；美团/京东优先填空。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import delete

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database import AppBase, AppSession, app_engine
from app.models import BrandStore

DATA_DIR = Path(__file__).resolve().parent.parent / "DataProcess 2" / "data"

BRAND_META = {
    "kp": {"region": "城市"},
    "xj": {"region": "战区"},
    "zz": {"region": "大区"},
}


def clean_id(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
        return None
    s = str(v).strip()
    if s in ("", "\\", "/", "-", "nan", "None", "null", "NaN"):
        return None
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return s


def find_file(brand_key: str) -> Path:
    # 演示/公开仓约定文件名：品牌1门店表.xlsx / 品牌2门店表.xlsx / 品牌3门店表.xlsx
    label_map = {"kp": "品牌1", "xj": "品牌2", "zz": "品牌3"}
    label = label_map[brand_key]
    for f in DATA_DIR.iterdir():
        if "门店表" not in f.name or not f.name.endswith(".xlsx"):
            continue
        if label in f.name or f.name.startswith(f"{brand_key}_"):
            return f
    raise FileNotFoundError(f"找不到 {brand_key} 门店表: {DATA_DIR}")


def load_brand(brand: str) -> list[dict]:
    region_col = BRAND_META[brand]["region"]
    path = find_file(brand)
    df = pd.read_excel(path, sheet_name="门店名称")
    df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed")]]
    df = df.dropna(how="all").copy()

    merged: dict[str, dict] = {}
    order: list[str] = []
    for _, r in df.iterrows():
        name = str(r.get("门店名称") or "").strip()
        if not name or name.lower() == "nan":
            continue
        region = str(r.get(region_col) or "").strip()
        if region.lower() == "nan":
            region = ""
        mt = clean_id(r.get("美团门店ID"))
        elm = clean_id(r.get("饿了么门店ID"))
        jd = clean_id(r.get("京东门店ID")) if "京东门店ID" in df.columns else None

        if name not in merged:
            merged[name] = {
                "store_name": name,
                "region": region or None,
                "mt_id": mt,
                "elm_id": elm,
                "jd_id": jd,
                "remark": None,
                "_elm_alts": [],
            }
            order.append(name)
            continue

        cur = merged[name]
        if not cur["region"] and region:
            cur["region"] = region
        if not cur["mt_id"] and mt:
            cur["mt_id"] = mt
        elif cur["mt_id"] and mt and cur["mt_id"] != mt:
            note = f"美团ID冲突保留{cur['mt_id']}另有{mt}"
            cur["remark"] = f"{cur['remark']}; {note}" if cur["remark"] else note
        if not cur["jd_id"] and jd:
            cur["jd_id"] = jd
        elif cur["jd_id"] and jd and cur["jd_id"] != jd:
            note = f"京东ID冲突保留{cur['jd_id']}另有{jd}"
            cur["remark"] = f"{cur['remark']}; {note}" if cur["remark"] else note
        if elm:
            if not cur["elm_id"]:
                cur["elm_id"] = elm
            elif cur["elm_id"] != elm:
                cur["_elm_alts"].append(elm)

    rows = []
    for name in order:
        cur = merged[name]
        alts = cur.pop("_elm_alts")
        if alts:
            note = f"饿了么ID另有{','.join(alts)}"
            cur["remark"] = f"{cur['remark']}; {note}" if cur["remark"] else note
        rows.append(cur)
    print(f"{brand}: {path.name} raw={len(df)} merged={len(rows)}")
    for r in rows:
        if r["remark"]:
            print(f"  merge-note {r['store_name']}: {r['remark']}")
    return rows


def main() -> None:
    AppBase.metadata.create_all(bind=app_engine)
    db = AppSession()
    try:
        total = 0
        for brand in ("kp", "xj", "zz"):
            rows = load_brand(brand)
            deleted = db.execute(delete(BrandStore).where(BrandStore.brand == brand)).rowcount
            for r in rows:
                db.add(
                    BrandStore(
                        brand=brand,
                        store_name=r["store_name"],
                        enabled=True,
                        mt_id=r["mt_id"],
                        elm_id=r["elm_id"],
                        jd_id=r["jd_id"],
                        region=r["region"],
                        remark=r["remark"],
                    )
                )
            total += len(rows)
            print(f"  -> deleted={deleted} inserted={len(rows)}")
        db.commit()
        for brand in ("kp", "xj", "zz"):
            n = db.query(BrandStore).filter(BrandStore.brand == brand).count()
            print(f"verify {brand}: {n}")
        print(f"DONE total={total} -> {app_engine.url}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
