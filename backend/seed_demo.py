"""生成 SQLite 演示数据，供本地连不上 MySQL 时跑通看板。

用法：cd backend && .venv/bin/python seed_demo.py

按 config.BRANDS + brand_columns() 为每个品牌建导入后的业务表
（account / order / product / exposure / info，kp 另有 profit、activity）。
列名走品牌映射：kp 无订单编号、xj 用店铺ID/下单时间/战区/机构编码、zz 用大区。
门店 / 商品 / 区域名均为脱敏占位（品牌1-3、门店N、商品N），表结构与线上一致。
"""
import os
import random
import sqlite3
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from app.config import BRANDS, brand_columns  # noqa: E402

random.seed(42)

# 含今天在内的最近 30 天
DAYS = 30
TODAY = date.today()
# 三餐：与导入脚本一致，早餐 23:00-10:00、午餐 10:00-14:00、晚餐 14:00-23:00
MEAL_HOURS = {
    "早餐": [7, 8, 9, 23],
    "午餐": [10, 11, 12, 13],
    "晚餐": [14, 15, 16, 17, 18, 19, 20, 21, 22],
}
MEAL_WEIGHTS = [("早餐", 2), ("午餐", 5), ("晚餐", 4)]

# kp 活动：出现概率、商家支出区间（元）。减配送费几乎每单都有。
# 一单多个活动时，营业额整单计入每个分类，支出只计该分类。
KP_ACTIVITIES = {
    "美团": [
        ("减配送费", 1.0, (2.5, 4.5)),
        ("支付红包", 0.70, (8.0, 16.0)),
        ("商品折扣", 0.34, (6.0, 18.0)),
        ("商家代金券", 0.17, (1.0, 3.0)),
        ("满减", 0.13, (3.0, 8.0)),
        ("商品折扣券", 0.02, (8.0, 16.0)),
        ("减配追补", 0.005, (0.0, 0.0)),
    ],
    "饿了么": [
        ("减配送费", 1.0, (2.5, 4.0)),
        ("爆单红包", 0.55, (8.0, 18.0)),
        ("超抢手", 0.44, (10.0, 22.0)),
        ("关注有礼", 0.18, (1.0, 1.0)),
        ("特价菜", 0.12, (3.0, 16.0)),
        ("满减", 0.12, (3.0, 6.0)),
        ("平台活动", 0.09, (0.0, 0.0)),
        ("粉丝群专享券", 0.05, (1.0, 4.0)),
        ("下单返券", 0.04, (4.0, 8.0)),
        ("集点返券", 0.02, (6.0, 10.0)),
    ],
}

# 门店 / 区域 / 商品均为脱敏占位；门店 ID 为假数据，饿了么/京东 ID 按平台错开
# region 是 info 树和销售表共用的分组名（kp=城市，xj=战区，zz=大区）
FIXTURES: dict[str, dict] = {
    "kp": {
        "platforms": ["美团", "饿了么"],
        "groups": {
            "区域1": [
                ("门店1", "10001"),
                ("门店2", "10002"),
                ("门店3", "10003"),
                ("门店4", "10004"),
            ],
            "区域2": [
                ("门店5", "10005"),
                ("门店6", "10006"),
                ("门店7", "10007"),
            ],
            "区域3": [
                ("门店8", "10008"),
                ("门店9", "10009"),
            ],
            "区域4": [
                ("门店10", "10010"),
                ("门店11", "10011"),
            ],
            "区域5": [
                ("门店12", "10012"),
                ("门店13", "10013"),
            ],
        },
        "products": [
            ("商品1", 48),
            ("商品2", 32),
            ("商品3", 28),
            ("商品4", 36),
            ("商品5", 42),
            ("商品6", 26),
            ("商品7", 6),
            ("商品8", 68),
        ],
        "ticket": (32, 95),
        "daily_orders": (8, 28),
        "scale": 1.0,
    },
    "xj": {
        "platforms": ["美团", "饿了么", "京东"],
        "groups": {
            "区域A": [
                ("门店14", "20001"),
                ("门店15", "20002"),
                ("门店16", "20003"),
                ("门店17", "20004"),
                ("门店18", "20005"),
            ],
            "区域B": [
                ("门店19", "20006"),
                ("门店20", "20007"),
            ],
            "区域C": [
                ("门店21", "20008"),
                ("门店22", "20009"),
            ],
        },
        "products": [
            ("商品9", 29.9, "分类1"),
            ("商品10", 32.0, "分类2"),
            ("商品11", 18.8, "分类1"),
            ("商品12", 16.8, "分类3"),
            ("商品13", 12.9, "分类4"),
            ("商品14", 39.9, "分类1"),
            ("商品15", 15.8, "分类4"),
            ("商品16", 22.0, "分类3"),
            ("商品17", 32.0, "分类2"),
            ("商品18", 24.8, "分类3"),
        ],
        "ticket": (28, 120),
        "daily_orders": (6, 22),
        "scale": 0.85,
    },
    "zz": {
        "platforms": ["美团", "饿了么"],
        "groups": {
            "区域X": [
                ("门店23", "30001"),
                ("门店24", "30002"),
                ("门店25", "30003"),
                ("门店26", "30004"),
            ],
            "区域Y": [
                ("门店27", "30005"),
                ("门店28", "30006"),
                ("门店29", "30007"),
                ("门店30", "30008"),
            ],
            "区域Z": [
                ("门店31", "30009"),
                ("门店32", "30010"),
            ],
        },
        "products": [
            ("商品19", 70),
            ("商品20", 68),
            ("商品21", 78),
            ("商品22", 36),
            ("商品23", 58),
            ("商品24", 62),
            ("商品25", 45),
            ("商品26", 128),
        ],
        "ticket": (18, 55),
        "daily_orders": (4, 16),
        "scale": 0.55,
    },
}


def _meal(hour: int) -> str:
    if hour >= 23 or hour < 10:
        return "早餐"
    if hour < 14:
        return "午餐"
    return "晚餐"


def _band_kp(amount: float) -> str:
    if amount < 40:
        return "0-40元"
    if amount < 60:
        return "40-60元"
    if amount < 85:
        return "60-85元"
    return "85元以上"


def _band_zz(amount: float) -> str:
    if amount < 15:
        return "0-15元"
    if amount < 20:
        return "15-20元"
    if amount < 25:
        return "20-25元"
    return "25元以上"


def _band_xj_amount(amount: float) -> str:
    if amount < 38:
        return "30-38元"
    if amount < 49:
        return "38-49元"
    if amount < 69:
        return "49-69元"
    if amount < 89:
        return "69-89元"
    if amount < 120:
        return "89-120元"
    return "120元以上"


def _band_xj_paid(paid: float) -> str:
    if paid < 30:
        return "0-30元"
    return _band_xj_amount(paid)


def _amount_class(brand: str, amount: float, paid: float) -> tuple[str, str]:
    if brand == "xj":
        return _band_xj_amount(amount), _band_xj_paid(paid)
    if brand == "zz":
        return _band_zz(amount), _band_zz(paid)
    return _band_kp(amount), _band_kp(paid)


def _kp_order_activities(platform: str, amount: float, paid: float) -> list[tuple[str, float]]:
    """为一笔 kp 订单抽出活动分类和商家支出。支出合计不超过该单折扣。"""
    picked = []
    for name, prob, (lo, hi) in KP_ACTIVITIES[platform]:
        if random.random() < prob:
            spend = 0.0 if hi <= 0 else round(random.uniform(lo, hi), 2)
            picked.append([name, spend])
    if not picked:
        picked.append(["减配送费", round(random.uniform(2.5, 4.0), 2)])
    discount = max(round(amount - paid, 2), 0.0)
    total = sum(s for _, s in picked)
    if total > discount > 0:
        scale = discount / total
        for item in picked:
            item[1] = round(item[1] * scale, 2)
    elif discount == 0:
        for item in picked:
            item[1] = 0.0
    return [(name, spend) for name, spend in picked]


def _platform_store_id(mt_id: str, platform: str) -> str:
    """同一门店各平台 ID 不同，和导入后销售表的实际情况一致。"""
    base = int(mt_id)
    if platform == "饿了么":
        return str(base + 1_000_000)
    if platform == "京东":
        return str(base + 2_000_000)
    return mt_id


def _create(cur, table: str, cols: dict[str, str | None]) -> None:
    defs = []
    for logical, actual in cols.items():
        if not actual:
            continue
        if logical == "id":
            defs.append(f'"{actual}" INTEGER PRIMARY KEY')
        else:
            defs.append(f'"{actual}" TEXT')
    cur.execute(f"CREATE TABLE {table} ({', '.join(defs)})")


def _rows_to_sql(cols: dict[str, str | None], rows: list[dict]) -> tuple[str, list[list]]:
    """把逻辑字段行翻译成实际列名的批量插入参数。"""
    used = [(k, cols[k]) for k in rows[0] if cols.get(k)]
    names = ", ".join(f'"{actual}"' for _, actual in used)
    marks = ", ".join("?" for _ in used)
    params = [[row.get(k) for k, _ in used] for row in rows]
    return f"INSERT INTO {{table}} ({names}) VALUES ({marks})", params


def main() -> None:
    db_path = os.path.join(os.path.dirname(__file__), "demo.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    order_seq = 100000

    for brand, cfg in BRANDS.items():
        fix = FIXTURES[brand]
        tb = cfg["tables"]
        tables = [t for t in ("account", "order", "product", "exposure", "info", "profit", "activity") if t in tb]
        cols = {t: brand_columns(brand, t) for t in tables}
        for ttype in tables:
            _create(cur, tb[ttype], cols[ttype])

        stores = []
        for region, items in fix["groups"].items():
            for name, mt_id in items:
                stores.append({"name": name, "mt": mt_id, "region": region, "org": f"{brand.upper()}{mt_id[-4:]}"})

        # 机构树：品牌根 -> 城市/战区/大区 -> 门店。叶子名称与销售表门店名称一致，筛选树才能对上。
        info_rows = []
        root_id = 1
        info_rows.append({"id": root_id, "store_name": cfg["label"], "p_id": 0, "create_time": now})
        next_id = 2
        region_ids = {}
        for region in fix["groups"]:
            region_ids[region] = next_id
            info_rows.append({"id": next_id, "store_name": region, "p_id": root_id, "create_time": now})
            next_id += 1
        for store in stores:
            info_rows.append({
                "id": next_id,
                "store_name": store["name"],
                "p_id": region_ids[store["region"]],
                "create_time": now,
            })
            next_id += 1
        sql, params = _rows_to_sql(cols["info"], info_rows)
        cur.executemany(sql.format(table=tb["info"]), params)

        lo, hi = fix["daily_orders"]
        ticket_lo, ticket_hi = fix["ticket"]
        products = fix["products"]
        account_rows, order_rows, product_rows, exposure_rows, profit_rows = [], [], [], [], []
        # (日期, 门店id, 门店名称, 平台, 城市, 活动分类) -> 营业额 / 支出 / 订单数
        activity_acc: dict[tuple, dict] = {}

        for d in range(DAYS):
            day = TODAY - timedelta(days=DAYS - 1 - d)
            weekend = 1.25 if day.weekday() >= 5 else 1.0
            growth = 1 + d / DAYS * 0.12
            for store in stores:
                for plat in fix["platforms"]:
                    n_orders = max(1, int(random.randint(lo, hi) * fix["scale"] * weekend * growth))
                    sid = _platform_store_id(store["mt"], plat)
                    revenue = 0.0
                    for _ in range(n_orders):
                        order_seq += 1
                        meal = random.choices(
                            [m for m, _ in MEAL_WEIGHTS],
                            weights=[w for _, w in MEAL_WEIGHTS],
                        )[0]
                        hour = random.choice(MEAL_HOURS[meal])
                        amount = round(random.uniform(ticket_lo, ticket_hi), 2)
                        # 实付约为订单金额的 75%-92%，和导入后的折扣结构接近
                        paid = round(amount * random.uniform(0.75, 0.92), 2)
                        amount_class, paid_class = _amount_class(brand, amount, paid)
                        revenue += amount
                        joined = "否"
                        if brand == "kp":
                            for cat, spend in _kp_order_activities(plat, amount, paid):
                                joined = "是"
                                key = (str(day), sid, store["name"], plat, store["region"], cat)
                                slot = activity_acc.setdefault(
                                    key, {"revenue": 0.0, "spend": 0.0, "orders": 0},
                                )
                                slot["revenue"] += amount
                                slot["spend"] += spend
                                slot["orders"] += 1
                        order_rows.append({
                            "order_id": f"{order_seq}",
                            "store_id": sid,
                            "store_name": store["name"],
                            "time": f"{day} {hour:02d}:{random.randint(0, 59):02d}:{random.randint(0, 59):02d}",
                            "amount": f"{amount:.2f}",
                            "paid": f"{paid:.2f}",
                            "platform": plat,
                            "meal_type": meal,
                            "is_activity": joined if brand == "kp" else random.choices(["是", "否"], weights=[3, 7])[0],
                            "amount_class": amount_class,
                            "paid_class": paid_class,
                            "region": store["region"],
                            "org_code": store["org"],
                            "create_time": now,
                        })

                    revenue = round(revenue, 2)
                    commission = round(revenue * random.uniform(0.06, 0.12), 2)
                    subsidy = round(revenue * random.uniform(0.12, 0.22), 2)
                    income = round(max(revenue - commission - subsidy * 0.55, 0), 2)
                    account_rows.append({
                        "date": str(day),
                        "store_id": sid,
                        "store_name": store["name"],
                        "platform": plat,
                        "revenue": f"{revenue:.2f}",
                        "orders": str(n_orders),
                        "commission": f"{commission:.2f}",
                        "subsidy": f"{subsidy:.2f}",
                        "income": f"{income:.2f}",
                        "region": store["region"],
                        "org_code": store["org"],
                        "create_time": now,
                    })

                    # 商品销售额按当日营业额拆开，避免商品榜和 KPI 完全对不上
                    picked = random.sample(products, k=min(5, len(products)))
                    weights = [random.random() for _ in picked]
                    total_w = sum(weights)
                    for item, w in zip(picked, weights):
                        name = item[0]
                        price = item[1]
                        share = revenue * (w / total_w) * random.uniform(0.85, 1.05)
                        qty = max(1, int(share / price))
                        amount = round(qty * price, 2)
                        product_rows.append({
                            "date": str(day) if brand != "xj" else f"{day} 00:00:00",
                            "store_id": sid,
                            "store_name": store["name"],
                            "platform": plat,
                            "name": name,
                            "qty": str(qty),
                            "amount": f"{amount:.2f}",
                            "region": store["region"],
                            "org_code": store["org"],
                            "category": item[2] if len(item) > 2 else None,
                            "create_time": now,
                        })

                    orderers = max(1, int(n_orders * random.uniform(0.82, 0.98)))
                    visitors = max(orderers + 1, int(orderers / random.uniform(0.18, 0.32)))
                    exposure = max(visitors + 1, int(visitors / random.uniform(0.08, 0.14)))
                    new_c = int(orderers * random.uniform(0.35, 0.55))
                    exposure_rows.append({
                        "date": str(day),
                        "store_id": sid,
                        "store_name": store["name"],
                        "platform": plat,
                        "region": store["region"],
                        "org_code": store["org"],
                        "exposure": str(exposure),
                        "visitors": str(visitors),
                        "orderers": str(orderers),
                        "new_customers": str(new_c),
                        "old_customers": str(orderers - new_c),
                        "create_time": now,
                    })

                    if "profit" in cols:
                        offline = round(revenue * random.uniform(1.05, 1.35), 2)
                        cost = round(offline * random.uniform(0.55, 0.72), 2)
                        profit = round(income - cost * 0.35, 2)
                        profit_rows.append({
                            "order_id": f"P{order_seq}",
                            "settlement_amount": f"{income:.2f}",
                            "revenue": f"{revenue:.2f}",
                            "store_id": sid,
                            "store_name": store["name"],
                            "bill_date": str(day),
                            "offline_revenue": f"{offline:.2f}",
                            "cost_amount": f"{cost:.2f}",
                            "cost_rate": f"{(cost / offline):.4f}" if offline else "0",
                            "profit_amount": f"{profit:.2f}",
                            "profit_rate": f"{(profit / revenue):.4f}" if revenue else "0",
                            "city": store["region"],
                            "platform": plat,
                            "create_time": now,
                        })

        batches = {
            "account": account_rows,
            "order": order_rows,
            "product": product_rows,
            "exposure": exposure_rows,
        }
        if profit_rows:
            batches["profit"] = profit_rows
        if activity_acc:
            batches["activity"] = [
                {
                    "date": day,
                    "store_id": sid,
                    "store_name": name,
                    "platform": plat,
                    "region": region,
                    "category": cat,
                    "revenue": f"{slot['revenue']:.2f}",
                    "merchant_spend": f"{slot['spend']:.2f}",
                    "orders": str(slot["orders"]),
                    "create_time": now,
                }
                for (day, sid, name, plat, region, cat), slot in activity_acc.items()
            ]
        for ttype, rows in batches.items():
            sql, params = _rows_to_sql(cols[ttype], rows)
            cur.executemany(sql.format(table=tb[ttype]), params)
            print(f"  {tb[ttype]}: {len(rows)} 行")

    conn.commit()
    conn.close()
    print(f"demo.db 已生成：{db_path}")
    print(f"品牌 {', '.join(BRANDS)} × {DAYS} 天，截止日期 {TODAY}")


if __name__ == "__main__":
    main()
