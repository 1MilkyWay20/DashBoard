"""看板查询：所有业务库 SQL 组装集中在这里。

按 AGENTS.md 约定：只用 config 的逻辑字段名拼查询，
业务代码里不出现具体品牌表名和中文列名。
"""
from datetime import date, timedelta

from sqlalchemy import func, select, column, table, text
from sqlalchemy.engine import Connection

from .. import config

SALES_KEYS = ["date", "store_id", "store_name", "platform", "region",
              "revenue", "orders", "commission", "subsidy", "income"]
ORDER_KEYS = ["order_id", "time", "store_id", "store_name", "platform", "meal_type"]
PRODUCT_KEYS = ["date", "store_id", "store_name", "platform", "name", "qty", "amount"]
# 利润表（当前仅 kp）：门店排行附利润 / 线下金额
PROFIT_KEYS = ["bill_date", "store_id", "store_name", "platform",
               "profit_amount", "offline_revenue"]
# 曝光/流量表：人数类指标跨平台加总后算转化率
EXPOSURE_KEYS = ["date", "store_id", "store_name", "platform", "region",
                 "exposure", "visitors", "orderers"]
# 营销活动表（当前仅 kp）：按活动分类汇总
ACTIVITY_KEYS = ["date", "store_id", "store_name", "platform", "category", "revenue", "merchant_spend", "orders"]
# 异常订单（当前仅 xj 美团）：按门店 × 商家服务问题计数
ABNORMAL_KEYS = ["time", "store_id", "store_name", "platform", "issue"]


TOP_PRODUCT_N = 200  # 商品排行最多返回条数（前端分页展示）


def _sales(brand: str):
    """销售数据表 -> (表对象, {逻辑名: 列表达式})"""
    c = config.brand_columns(brand, "account")
    keys = [k for k in SALES_KEYS if c.get(k)]  # 覆盖为 None = 该品牌无此列
    t = table(config.table_name(brand, "account"), *[column(c[k]) for k in keys])
    return t, {k: t.c[c[k]] for k in keys}


def _order(brand: str):
    c = config.brand_columns(brand, "order")
    keys = [k for k in ORDER_KEYS if c.get(k)]
    t = table(config.table_name(brand, "order"), *[column(c[k]) for k in keys])
    return t, {k: t.c[c[k]] for k in keys}


def _product(brand: str):
    c = config.brand_columns(brand, "product")
    keys = [k for k in PRODUCT_KEYS if c.get(k)]
    t = table(config.table_name(brand, "product"), *[column(c[k]) for k in keys])
    return t, {k: t.c[c[k]] for k in keys}


def _profit(brand: str):
    """利润表 -> (表对象, {逻辑名: 列表达式})；仅配置了 profit 表的品牌可用。"""
    c = config.brand_columns(brand, "profit")
    keys = [k for k in PROFIT_KEYS if c.get(k)]
    t = table(config.table_name(brand, "profit"), *[column(c[k]) for k in keys])
    return t, {k: t.c[c[k]] for k in keys}


def _info(brand: str):
    """机构信息表（id / 机构名称 / pid），用于门店树父级。"""
    c = config.brand_columns(brand, "info")
    keys = [k for k in ("id", "store_name", "p_id") if c.get(k)]
    t = table(config.table_name(brand, "info"), *[column(c[k]) for k in keys])
    return t, {k: t.c[c[k]] for k in keys}


def _exposure(brand: str):
    """曝光/流量表 -> (表对象, {逻辑名: 列表达式})"""
    c = config.brand_columns(brand, "exposure")
    keys = [k for k in EXPOSURE_KEYS if c.get(k)]
    t = table(config.table_name(brand, "exposure"), *[column(c[k]) for k in keys])
    return t, {k: t.c[c[k]] for k in keys}


def _activity(brand: str):
    """营销活动表 -> (表对象, {逻辑名: 列表达式})；仅配置了 activity 表的品牌可用。"""
    c = config.brand_columns(brand, "activity")
    keys = [k for k in ACTIVITY_KEYS if c.get(k)]
    t = table(config.table_name(brand, "activity"), *[column(c[k]) for k in keys])
    return t, {k: t.c[c[k]] for k in keys}


def _abnormal(brand: str):
    """异常订单表 -> (表对象, {逻辑名: 列表达式})；仅配置了 abnormal 表的品牌可用。"""
    c = config.brand_columns(brand, "abnormal")
    keys = [k for k in ABNORMAL_KEYS if c.get(k)]
    t = table(config.table_name(brand, "abnormal"), *[column(c[k]) for k in keys])
    return t, {k: t.c[c[k]] for k in keys}


def _exposure_rates(exposure: int, visitors: int, orderers: int) -> dict:
    """人数加总后再算转化率（不做比率平均）。"""
    return {
        "exposure": exposure,
        "visitors": visitors,
        "orderers": orderers,
        # 入店转化率 = 入店人数 / 曝光人数
        "visit_rate": round(visitors / exposure, 4) if exposure else 0,
        # 下单转化率 = 下单人数 / 入店人数
        "order_rate": round(orderers / visitors, 4) if visitors else 0,
    }


def _apply_filters(stmt, date_col, start, end, platforms, store_ids, plat_col, store_col):
    """公共过滤：时间范围 + 平台 + 门店。

    用半开区间 [start, end+1day) 而不是 DATE(列)，以便走 (日期/下单时间, …) 索引。
    DATE 列与 DATETIME 列都适用（导入侧日表存 DATE，订单表存 DATETIME）。
    """
    if start:
        stmt = stmt.where(date_col >= start)
    if end:
        stmt = stmt.where(date_col < end + timedelta(days=1))
    if platforms:
        stmt = stmt.where(plat_col.in_(platforms))
    if store_ids:
        stmt = stmt.where(store_col.in_(store_ids))
    return stmt


def _ratios(agg: dict) -> dict:
    """聚合后计算比率类指标（不做比率平均）。"""
    revenue = agg["revenue"] or 0
    orders = agg["orders"] or 0
    return {
        **agg,
        "avg_order_value": round(revenue / orders, 2) if orders else 0,      # 客单价 = 营业额/有效订单数
        "income_rate": round((agg["income"] or 0) / revenue, 4) if revenue else 0,      # 实收率
        "commission_rate": round((agg["commission"] or 0) / revenue, 4) if revenue else 0,  # 平台佣金占比
        "subsidy_rate": round((agg["subsidy"] or 0) / revenue, 4) if revenue else 0,        # 活动支出占比（商家补贴/营业额）
    }


def period_summary(conn: Connection, brand: str, start: date, end: date,
                   platforms: list[str] | None, store_ids: list[str] | None) -> dict:
    """一个周期的 9 项 KPI。"""
    t, m = _sales(brand)
    stmt = select(
        func.coalesce(func.sum(m["revenue"]), 0).label("revenue"),
        func.coalesce(func.sum(m["orders"]), 0).label("orders"),
        func.coalesce(func.sum(m["income"]), 0).label("income"),
        func.coalesce(func.sum(m["commission"]), 0).label("commission"),
        func.coalesce(func.sum(m["subsidy"]), 0).label("subsidy"),
    )
    stmt = _apply_filters(stmt, m["date"], start, end, platforms, store_ids, m["platform"], m["store_id"])
    row = conn.execute(stmt).mappings().one()
    agg = {k: float(row[k]) if k != "orders" else int(row[k]) for k in
           ("revenue", "orders", "income", "commission", "subsidy")}
    return _ratios(agg)


def summary_with_compare(conn, brand, start, end, platforms, store_ids) -> dict:
    """当前周期 KPI + 上一等长周期环比。"""
    days = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    cur = period_summary(conn, brand, start, end, platforms, store_ids)
    prev = period_summary(conn, brand, prev_start, prev_end, platforms, store_ids)
    return {
        "current": cur,
        "previous": prev,
        "range": {"start": str(start), "end": str(end)},
        "prev_range": {"start": str(prev_start), "end": str(prev_end)},
    }


def trend(conn: Connection, brand, start, end, platforms, store_ids) -> list[dict]:
    """按天：营业额 / 订单数 / 收入 / 佣金 / 商补，比率在聚合后计算。"""
    t, m = _sales(brand)
    # 销售表日期列为 DATE，直接 GROUP BY 即可（避免 DATE() 阻碍优化器）
    d = m["date"].label("date")
    stmt = (
        select(
            d,
            func.coalesce(func.sum(m["revenue"]), 0).label("revenue"),
            func.coalesce(func.sum(m["orders"]), 0).label("orders"),
            func.coalesce(func.sum(m["income"]), 0).label("income"),
            func.coalesce(func.sum(m["commission"]), 0).label("commission"),
            func.coalesce(func.sum(m["subsidy"]), 0).label("subsidy"),
        )
        .group_by(m["date"])
        .order_by(m["date"])
    )
    stmt = _apply_filters(stmt, m["date"], start, end, platforms, store_ids, m["platform"], m["store_id"])
    out = []
    for r in conn.execute(stmt).mappings():
        agg = {
            "revenue": float(r["revenue"]),
            "orders": int(r["orders"]),
            "income": float(r["income"]),
            "commission": float(r["commission"]),
            "subsidy": float(r["subsidy"]),
        }
        # 比率按当天聚合后算，不做比率平均
        row = _ratios(agg)
        row["date"] = str(r["date"])
        out.append(row)
    return out


def by_platform(conn: Connection, brand, start, end, platforms, store_ids) -> list[dict]:
    t, m = _sales(brand)
    p = m["platform"].label("platform")
    stmt = select(
        p,
        func.coalesce(func.sum(m["revenue"]), 0).label("revenue"),
        func.coalesce(func.sum(m["orders"]), 0).label("orders"),
        func.coalesce(func.sum(m["income"]), 0).label("income"),
        func.coalesce(func.sum(m["commission"]), 0).label("commission"),
        func.coalesce(func.sum(m["subsidy"]), 0).label("subsidy"),
    ).group_by(p).order_by(func.sum(m["revenue"]).desc())
    stmt = _apply_filters(stmt, m["date"], start, end, platforms, store_ids, m["platform"], m["store_id"])
    return [dict(r) for r in conn.execute(stmt).mappings()]


def by_store(conn: Connection, brand, start, end, platforms, store_ids) -> list[dict]:
    """门店排行，按门店名称汇总。

    选一个或多个平台都只做过滤，不按平台拆行；金额/订单先加总，
    实收率/活动支出占比/佣金占比/客单价在加总后计算，不做比率平均。

    鱇脯（kp）额外挂利润表：利润、结算占比（收入/线下金额）、利润率（利润/营业额）。
    """
    t, m = _sales(brand)
    sname = m["store_name"].label("store_name")
    stmt = select(
        sname,
        func.coalesce(func.sum(m["revenue"]), 0).label("revenue"),
        func.coalesce(func.sum(m["orders"]), 0).label("orders"),
        func.coalesce(func.sum(m["income"]), 0).label("income"),
        func.coalesce(func.sum(m["commission"]), 0).label("commission"),
        func.coalesce(func.sum(m["subsidy"]), 0).label("subsidy"),
    ).group_by(sname).order_by(func.sum(m["revenue"]).desc())
    stmt = _apply_filters(stmt, m["date"], start, end, platforms, store_ids, m["platform"], m["store_id"])
    out = []
    for r in conn.execute(stmt).mappings():
        agg = {
            "store_name": r["store_name"],
            "revenue": float(r["revenue"] or 0),
            "orders": int(r["orders"] or 0),
            "income": float(r["income"] or 0),
            "commission": float(r["commission"] or 0),
            "subsidy": float(r["subsidy"] or 0),
        }
        # 比率/客单价按门店加总后算：活动支出占比=商补/营业额，佣金占比，客单价=营业额/订单
        out.append(_ratios(agg))

    # 仅配置了利润表的品牌（当前只有 kp）追加利润相关指标
    if config.has_table(brand, "profit"):
        _attach_store_profit(conn, brand, start, end, platforms, store_ids, out)
    return out


def _attach_store_profit(
    conn: Connection, brand, start, end, platforms, store_ids, rows: list[dict],
) -> None:
    """按门店名称合并利润表加总结果，并重算结算占比 / 利润率。

    结算占比 = Σ收入 / Σ线下金额；利润率 = Σ利润 / Σ营业额（营业额取销售表加总）。
    """
    t, m = _profit(brand)
    sname = m["store_name"].label("store_name")
    stmt = select(
        sname,
        func.coalesce(func.sum(m["profit_amount"]), 0).label("profit"),
        func.coalesce(func.sum(m["offline_revenue"]), 0).label("offline_revenue"),
    ).group_by(sname)
    stmt = _apply_filters(
        stmt, m["bill_date"], start, end, platforms, store_ids, m["platform"], m["store_id"],
    )
    by_name = {
        r["store_name"]: {
            "profit": float(r["profit"] or 0),
            "offline_revenue": float(r["offline_revenue"] or 0),
        }
        for r in conn.execute(stmt).mappings()
    }
    for row in rows:
        p = by_name.get(row["store_name"], {"profit": 0.0, "offline_revenue": 0.0})
        profit = p["profit"]
        offline = p["offline_revenue"]
        revenue = row["revenue"] or 0
        income = row["income"] or 0
        row["profit"] = round(profit, 2)
        row["offline_revenue"] = round(offline, 2)
        # 结算占比 = 收入 / 线下金额；利润率 = 利润 / 营业额（均聚合后算）
        row["settlement_rate"] = round(income / offline, 4) if offline else 0
        row["profit_rate"] = round(profit / revenue, 4) if revenue else 0


def meal_type(conn: Connection, brand, start, end, platforms, store_ids) -> list[dict]:
    """三餐时段订单占比（来自订单表）。"""
    t, m = _order(brand)
    mt = m["meal_type"].label("meal_type")
    if "order_id" in m:
        cnt = func.count(func.distinct(m["order_id"])).label("order_count")
    else:
        cnt = func.count().label("order_count")  # 无订单编号列，每行即一单
    stmt = select(mt, cnt).group_by(mt)
    stmt = _apply_filters(stmt, m["time"], start, end, platforms, store_ids, m["platform"], m["store_id"])
    return [dict(r) for r in conn.execute(stmt).mappings()]


def top_products(
    conn: Connection, brand, start, end, platforms, store_ids,
    limit: int | None = TOP_PRODUCT_N,
) -> list[dict]:
    """商品排行：按销售额排序并返回销量。

    limit 默认 TOP_PRODUCT_N（前端分页）；传 None 表示不截断（供 AI 全量分析）。
    """
    t, m = _product(brand)
    name = m["name"].label("name")
    stmt = select(
        name,
        func.coalesce(func.sum(m["qty"]), 0).label("qty"),
        func.coalesce(func.sum(m["amount"]), 0).label("amount"),
    ).group_by(name).order_by(func.sum(m["amount"]).desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    stmt = _apply_filters(stmt, m["date"], start, end, platforms, store_ids, m["platform"], m["store_id"])
    out = []
    for r in conn.execute(stmt).mappings():
        out.append({
            "name": r["name"],
            "qty": float(r["qty"] or 0),
            "amount": float(r["amount"] or 0),
        })
    return out


def product_trend(
    conn: Connection, brand, start, end, platforms, store_ids, name: str
) -> list[dict]:
    """指定商品按日的销售额、销量趋势。"""
    t, m = _product(brand)
    day = m["date"].label("date")
    stmt = (
        select(
            day,
            func.coalesce(func.sum(m["qty"]), 0).label("qty"),
            func.coalesce(func.sum(m["amount"]), 0).label("amount"),
        )
        .where(m["name"] == name)
        .group_by(day)
        .order_by(day)
    )
    stmt = _apply_filters(stmt, m["date"], start, end, platforms, store_ids, m["platform"], m["store_id"])
    out = []
    for r in conn.execute(stmt).mappings():
        out.append({
            "date": str(r["date"])[:10],
            "qty": float(r["qty"] or 0),
            "amount": float(r["amount"] or 0),
        })
    return out


def _day_agg(row) -> dict | None:
    """单日聚合行 -> 四项指标；当日无数据返回 None。"""
    if row is None:
        return None
    revenue = float(row["revenue"] or 0)
    orders = int(row["orders"] or 0)
    income = float(row["income"] or 0)
    return {
        "revenue": revenue,
        "orders": orders,
        "income": income,
        "income_rate": round(income / revenue, 4) if revenue else 0,  # 聚合后算实收率
    }


def latest_day_summary(conn: Connection, brand: str) -> dict | None:
    """品牌最近一天的四项指标 + 前一天数据（供前端算环比涨跌）。

    "最近一天"以销售数据表里的最大日期为准：数据 T+1 导入有延迟，
    按日历昨天查会查到空。无任何数据时返回 None。
    """
    t, m = _sales(brand)
    # 销售表存 DATE；直接 MAX/GROUP BY 日期列，走索引
    last = conn.execute(select(func.max(m["date"]))).scalar()
    if last is None:
        return None
    last = date.fromisoformat(str(last)[:10])  # SQLite 下 max() 可能返回字符串，统一转 date
    prev = last - timedelta(days=1)
    stmt = select(
        m["date"].label("day"),
        func.coalesce(func.sum(m["revenue"]), 0).label("revenue"),
        func.coalesce(func.sum(m["orders"]), 0).label("orders"),
        func.coalesce(func.sum(m["income"]), 0).label("income"),
    ).where(m["date"].in_([last, prev])).group_by(m["date"])
    rows = {date.fromisoformat(str(r["day"])[:10]): r for r in conn.execute(stmt).mappings()}
    return {
        "date": str(last),
        "current": _day_agg(rows.get(last)),
        "previous": _day_agg(rows.get(prev)),
    }


def _activity_metric_row(r, **extra) -> dict:
    """投入产出比 = Σ活动营业额 / Σ商家补贴，在分组加总之后计算。"""
    revenue = float(r["revenue"] or 0)
    spend = float(r["merchant_spend"] or 0)
    return {
        **extra,
        "revenue": round(revenue, 2),
        "merchant_spend": round(spend, 2),
        "orders": int(float(r["orders"] or 0)),
        "roi": round(revenue / spend, 2) if spend else 0,
    }


def _physical_table(conn: Connection, brand: str, ttype: str) -> bool:
    """配置里有这张表，并且业务库里也已经导入。未导入时看板按空数据展示。"""
    if not config.has_table(brand, ttype):
        return False
    name = config.table_name(brand, ttype)
    return conn.execute(text("SHOW TABLES LIKE :name"), {"name": name}).first() is not None


def _activity_grouped(conn, brand, start, end, platforms, store_ids, group_cols: list[str]):
    if not _physical_table(conn, brand, "activity"):
        return []
    t, m = _activity(brand)
    labels = [m[k].label(k) for k in group_cols]
    stmt = select(
        *labels,
        func.coalesce(func.sum(m["revenue"]), 0).label("revenue"),
        func.coalesce(func.sum(m["merchant_spend"]), 0).label("merchant_spend"),
        func.coalesce(func.sum(m["orders"]), 0).label("orders"),
    ).group_by(*labels)
    stmt = _apply_filters(
        stmt, m["date"], start, end, platforms, store_ids, m["platform"], m["store_id"],
    )
    return list(conn.execute(stmt).mappings())


def activity_by_category(
    conn: Connection, brand, start, end, platforms, store_ids
) -> list[dict]:
    """按活动分类汇总。"""
    out = [
        _activity_metric_row(r, category=r["category"] or "未知")
        for r in _activity_grouped(conn, brand, start, end, platforms, store_ids, ["category"])
    ]
    out.sort(key=lambda x: x["merchant_spend"], reverse=True)
    return out


def activity_by_store(
    conn: Connection, brand, start, end, platforms, store_ids
) -> list[dict]:
    """按门店汇总。同一门店跨活动类型加总，口径与分类表一致。"""
    out = [
        _activity_metric_row(r, store_name=r["store_name"] or "未知")
        for r in _activity_grouped(conn, brand, start, end, platforms, store_ids, ["store_name"])
    ]
    out.sort(key=lambda x: x["revenue"], reverse=True)
    return out


def activity_by_store_category(
    conn: Connection, brand, start, end, platforms, store_ids
) -> list[dict]:
    """按门店 × 活动分类汇总，供点选某一家门店后切换上方图表。"""
    out = [
        _activity_metric_row(
            r,
            store_name=r["store_name"] or "未知",
            category=r["category"] or "未知",
        )
        for r in _activity_grouped(
            conn, brand, start, end, platforms, store_ids, ["store_name", "category"],
        )
    ]
    out.sort(key=lambda x: (x["store_name"], -x["merchant_spend"]))
    return out


def abnormal_by_store(
    conn: Connection, brand, start, end, platforms, store_ids,
) -> dict:
    """透视表：门店为行，异常类型为列，附行合计与列合计。

    一单多个「商家服务问题」在导入时已拆成多行，这里按行计数。
    """
    empty = {"issues": [], "rows": [], "totals": {"total": 0}}
    if not _physical_table(conn, brand, "abnormal"):
        return empty
    t, m = _abnormal(brand)
    stmt = select(
        m["store_name"].label("store_name"),
        m["issue"].label("issue"),
        func.count().label("count"),
    ).group_by(m["store_name"], m["issue"])
    stmt = _apply_filters(
        stmt, m["time"], start, end, platforms, store_ids, m["platform"], m["store_id"],
    )
    by_store: dict[str, dict[str, int]] = {}
    issues: set[str] = set()
    for r in conn.execute(stmt).mappings():
        store = r["store_name"] or "未知门店"
        issue = r["issue"] or "未知"
        count = int(r["count"] or 0)
        if not count:
            continue
        issues.add(issue)
        by_store.setdefault(store, {})[issue] = count

    issue_list = sorted(issues)
    rows = []
    totals = {issue: 0 for issue in issue_list}
    totals["total"] = 0
    for store in sorted(by_store):
        counts = by_store[store]
        row_total = sum(counts.values())
        row = {"store_name": store, "total": row_total, **{issue: counts.get(issue, 0) for issue in issue_list}}
        rows.append(row)
        for issue in issue_list:
            totals[issue] += counts.get(issue, 0)
        totals["total"] += row_total
    return {"issues": issue_list, "rows": rows, "totals": totals}


def exposure_funnel(
    conn: Connection, brand, start, end, platforms, store_ids,
) -> dict:
    """流量漏斗：周期内曝光/入店/下单人数加总（多平台合并），并带转化率。"""
    t, m = _exposure(brand)
    stmt = select(
        func.coalesce(func.sum(m["exposure"]), 0).label("exposure"),
        func.coalesce(func.sum(m["visitors"]), 0).label("visitors"),
        func.coalesce(func.sum(m["orderers"]), 0).label("orderers"),
    )
    stmt = _apply_filters(
        stmt, m["date"], start, end, platforms, store_ids, m["platform"], m["store_id"],
    )
    row = conn.execute(stmt).mappings().one()
    return _exposure_rates(
        int(row["exposure"] or 0),
        int(row["visitors"] or 0),
        int(row["orderers"] or 0),
    )


def exposure_trend(
    conn: Connection, brand, start, end, platforms, store_ids,
) -> list[dict]:
    """按天×平台流量趋势：各平台分开返回，转化率在当日该平台聚合后计算。

    趋势图固定展示全部平台，调用方应传 platforms=None；仍保留参数以兼容统一过滤签名。
    """
    t, m = _exposure(brand)
    d = m["date"].label("date")
    p = m["platform"].label("platform")
    stmt = (
        select(
            d,
            p,
            func.coalesce(func.sum(m["exposure"]), 0).label("exposure"),
            func.coalesce(func.sum(m["visitors"]), 0).label("visitors"),
            func.coalesce(func.sum(m["orderers"]), 0).label("orderers"),
        )
        .group_by(m["date"], m["platform"])
        .order_by(m["date"], m["platform"])
    )
    # 趋势固定全平台：忽略 platforms 筛选
    stmt = _apply_filters(
        stmt, m["date"], start, end, None, store_ids, m["platform"], m["store_id"],
    )
    out = []
    for r in conn.execute(stmt).mappings():
        row = _exposure_rates(
            int(r["exposure"] or 0),
            int(r["visitors"] or 0),
            int(r["orderers"] or 0),
        )
        row["date"] = str(r["date"])[:10]
        row["platform"] = r["platform"] or "未知"
        out.append(row)
    return out


def meta_platforms(conn: Connection, brand: str) -> list[str]:
    t, m = _sales(brand)
    rows = conn.execute(select(func.distinct(m["platform"]))).scalars().all()
    return [r for r in rows if r]


def _account_name_to_ids(conn: Connection, brand: str, platform: str | None) -> dict[str, list[str]]:
    """门店名称 -> 销售表中的门店 id 列表（同店多平台会有多个 id）。"""
    t, m = _sales(brand)
    stmt = select(
        m["store_id"].label("store_id"),
        m["store_name"].label("store_name"),
    ).distinct()
    if platform:
        stmt = stmt.where(m["platform"] == platform)
    name_to_ids: dict[str, list[str]] = {}
    for r in conn.execute(stmt).mappings():
        name = r["store_name"]
        if not name:
            continue
        name_to_ids.setdefault(name, []).append(str(r["store_id"]))
    return name_to_ids


def _meta_stores_from_info(
    conn: Connection, brand: str, name_to_ids: dict[str, list[str]]
) -> dict | None:
    """用 info 机构树组装筛选树，跳过品牌根：区/战区/城市 → … → 门店。"""
    it, im = _info(brand)
    info_rows = list(conn.execute(
        select(
            im["id"].label("id"),
            im["store_name"].label("store_name"),
            im["p_id"].label("p_id"),
        )
    ).mappings())
    if not info_rows:
        return None

    nodes: dict[str, dict] = {}
    for r in info_rows:
        nid = str(r["id"])
        pid = str(r["p_id"]) if r["p_id"] is not None else "0"
        nodes[nid] = {"id": nid, "name": r["store_name"], "pid": pid, "child_ids": []}
    for nid, n in nodes.items():
        if n["pid"] in nodes:
            nodes[n["pid"]]["child_ids"].append(nid)

    roots = [n for n in nodes.values() if n["pid"] not in nodes]
    if not roots:
        return None

    node_stores: dict[str, list[str]] = {}

    def build(nid: str) -> dict | None:
        n = nodes[nid]
        child_ids = sorted(n["child_ids"], key=lambda i: nodes[i]["name"] or "")
        # 叶子且名称能对上销售门店 → 门店节点
        if not child_ids:
            ids = name_to_ids.get(n["name"]) or []
            if not ids:
                return None
            val = f"s:{n['name']}"
            node_stores[val] = ids
            return {"tree": {"value": val, "label": n["name"]}, "ids": ids}

        children = []
        ids: list[str] = []
        for cid in child_ids:
            built = build(cid)
            if not built:
                continue
            children.append(built["tree"])
            ids.extend(built["ids"])
        if not children:
            return None
        # 去重且保序
        uniq = list(dict.fromkeys(ids))
        val = f"n:{nid}"
        node_stores[val] = uniq
        return {
            "tree": {"value": val, "label": n["name"], "children": children},
            "ids": uniq,
        }

    tree: list[dict] = []
    # 跳过品牌根，从根的下一级开始（区域 / 城市 …）
    top_ids = []
    for root in roots:
        top_ids.extend(root["child_ids"])
    for tid in sorted(top_ids, key=lambda i: nodes[i]["name"] or ""):
        built = build(tid)
        if built:
            tree.append(built["tree"])

    # info 对不上的销售门店挂到「未分组」
    info_leaf_names = {n["name"] for n in nodes.values() if not n["child_ids"]}
    orphans = sorted(name for name in name_to_ids if name not in info_leaf_names)
    if orphans:
        o_children = []
        o_ids: list[str] = []
        for name in orphans:
            ids = name_to_ids[name]
            val = f"s:{name}"
            node_stores[val] = ids
            o_children.append({"value": val, "label": name})
            o_ids.extend(ids)
        oval = "n:__ungrouped__"
        node_stores[oval] = list(dict.fromkeys(o_ids))
        tree.append({"value": oval, "label": "未分组", "children": o_children})

    return {"tree": tree, "node_stores": node_stores} if tree else None


def _meta_stores_from_region(
    conn: Connection, brand: str, name_to_ids: dict[str, list[str]], platform: str | None
) -> dict:
    """无 info 树时的兜底：按销售表 region（城市/战区/大区）两级分组。"""
    t, m = _sales(brand)
    node_stores: dict[str, list[str]] = {}
    if "region" not in m:
        children = []
        all_ids: list[str] = []
        for name, ids in sorted(name_to_ids.items(), key=lambda x: x[0]):
            val = f"s:{name}"
            node_stores[val] = ids
            children.append({"value": val, "label": name})
            all_ids.extend(ids)
        return {"tree": children, "node_stores": node_stores}

    stmt = select(
        m["store_name"].label("store_name"),
        m["region"].label("region"),
    ).distinct()
    if platform:
        stmt = stmt.where(m["platform"] == platform)
    region_of: dict[str, str] = {}
    for r in conn.execute(stmt).mappings():
        if r["store_name"]:
            region_of[r["store_name"]] = r["region"] or "未分组"

    groups: dict[str, list[str]] = {}
    for name in name_to_ids:
        groups.setdefault(region_of.get(name, "未分组"), []).append(name)

    tree = []
    for region, names in sorted(groups.items(), key=lambda x: x[0]):
        children = []
        ids: list[str] = []
        for name in sorted(names):
            sids = name_to_ids[name]
            val = f"s:{name}"
            node_stores[val] = sids
            children.append({"value": val, "label": name})
            ids.extend(sids)
        rval = f"r:{region}"
        node_stores[rval] = list(dict.fromkeys(ids))
        tree.append({"value": rval, "label": region, "children": children})
    return {"tree": tree, "node_stores": node_stores}


def meta_stores(conn: Connection, brand: str, platform: str | None = None) -> dict:
    """门店树形选项。

    返回 { tree, node_stores }：
    - tree: 给前端 el-tree-select（跳过品牌根，含完整父级）
    - node_stores: 节点 value -> 下属门店 id 列表，选父级时展开汇总
    """
    name_to_ids = _account_name_to_ids(conn, brand, platform)
    try:
        from_info = _meta_stores_from_info(conn, brand, name_to_ids)
        if from_info:
            return from_info
    except Exception:
        pass
    return _meta_stores_from_region(conn, brand, name_to_ids, platform)
