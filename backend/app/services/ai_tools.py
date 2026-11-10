"""AI 白名单工具：只调已有看板聚合，筛选由 FilterContext 锁定，忽略模型传入的 brand/日期等。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.engine import Connection

from ..config import has_table
from . import dashboard

# 趋势最长天数（非 Top 截断；过长区间控 token）
TREND_MAX_DAYS = 31


@dataclass(frozen=True)
class FilterContext:
    """会话锁定的筛选；工具一律用此上下文，不可被模型改写。"""

    brand: str
    start: date
    end: date
    platforms: list[str] | None
    store_ids: list[str] | None


# OpenAI-compatible tools schema（不暴露 brand / 日期 / 门店，防止越权改范围）
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_kpi_summary",
            "description": "获取当前筛选下的 KPI 汇总（销售额、订单数、收入、佣金、商补、客单价、实收率等）及上一等长周期环比。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_trend",
            "description": "获取按天趋势（营业额、订单数等 KPI），最多返回 31 天。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_platform_compare",
            "description": "按平台对比营业额、订单、收入、佣金、商补。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_store_rank",
            "description": "门店排行（按营业额），返回当前筛选下全部门店。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_meal_share",
            "description": "三餐/时段订单占比。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_top",
            "description": "商品销量/销售额排行，返回当前筛选下全部商品。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_exposure_funnel",
            "description": "流量漏斗：曝光人数、入店人数、下单人数及转化率。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_activity_roi",
            "description": "营销活动：按分类汇总 + 全部门店汇总（仅配置了活动表的品牌有数据）。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_abnormal_orders",
            "description": "异常订单按门店计数汇总（仅配置了异常订单表的品牌有数据），返回全部门店。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
]

TOOL_NAMES = frozenset(t["function"]["name"] for t in TOOL_DEFINITIONS)

# 工具名 → 中文状态文案（SSE status）
TOOL_STATUS_LABELS: dict[str, str] = {
    "get_kpi_summary": "正在查询 KPI 汇总…",
    "get_daily_trend": "正在查询按天趋势…",
    "get_platform_compare": "正在查询平台对比…",
    "get_store_rank": "正在查询门店排行…",
    "get_meal_share": "正在查询时段占比…",
    "get_product_top": "正在查询商品 TOP…",
    "get_exposure_funnel": "正在查询流量漏斗…",
    "get_activity_roi": "正在查询营销活动…",
    "get_abnormal_orders": "正在查询异常订单…",
}


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _args(ctx: FilterContext) -> tuple:
    return ctx.brand, ctx.start, ctx.end, ctx.platforms, ctx.store_ids


def run_tool(name: str, conn: Connection, ctx: FilterContext) -> str:
    """执行白名单工具；未知名称返回错误 JSON。模型传入的参数一律忽略。"""
    if name not in TOOL_NAMES:
        return _dump({"error": f"未知工具: {name}"})

    brand, start, end, plats, store_ids = _args(ctx)

    if name == "get_kpi_summary":
        return _dump(dashboard.summary_with_compare(conn, brand, start, end, plats, store_ids))

    if name == "get_daily_trend":
        rows = dashboard.trend(conn, brand, start, end, plats, store_ids)
        if len(rows) > TREND_MAX_DAYS:
            rows = rows[-TREND_MAX_DAYS:]
        return _dump(rows)

    if name == "get_platform_compare":
        return _dump(dashboard.by_platform(conn, brand, start, end, plats, store_ids))

    if name == "get_store_rank":
        return _dump(dashboard.by_store(conn, brand, start, end, plats, store_ids))

    if name == "get_meal_share":
        return _dump(dashboard.meal_type(conn, brand, start, end, plats, store_ids))

    if name == "get_product_top":
        return _dump(dashboard.top_products(conn, brand, start, end, plats, store_ids, limit=None))

    if name == "get_exposure_funnel":
        if not has_table(brand, "exposure"):
            return _dump({"error": "当前品牌未配置流量表"})
        return _dump(dashboard.exposure_funnel(conn, brand, start, end, plats, store_ids))

    if name == "get_activity_roi":
        if not has_table(brand, "activity"):
            return _dump({"error": "当前品牌未配置营销活动表"})
        categories = dashboard.activity_by_category(conn, brand, start, end, plats, store_ids)
        stores = dashboard.activity_by_store(conn, brand, start, end, plats, store_ids)
        return _dump({
            "categories": categories,
            "stores": stores,
        })

    if name == "get_abnormal_orders":
        if not has_table(brand, "abnormal"):
            return _dump({"error": "当前品牌未配置异常订单表"})
        data = dashboard.abnormal_by_store(conn, brand, start, end, plats, store_ids)
        rows = sorted(data.get("rows") or [], key=lambda r: r.get("total") or 0, reverse=True)
        return _dump({
            "issues": data.get("issues") or [],
            "rows": rows,
            "totals": data.get("totals") or {},
        })

    return _dump({"error": f"未实现: {name}"})
