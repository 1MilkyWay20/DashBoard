"""云端 LLM tool-calling 编排；只通过白名单工具取聚合数据，结果以 SSE 事件流输出。"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
from sqlalchemy.engine import Engine

from ..config import (
    AI_API_BASE,
    AI_API_KEY,
    AI_ENABLED,
    AI_MAX_TOOL_ROUNDS,
    AI_MODEL,
    BRANDS,
)
from .ai_tools import TOOL_DEFINITIONS, TOOL_STATUS_LABELS, FilterContext, run_tool

logger = logging.getLogger(__name__)

HISTORY_MAX_TURNS = 6  # 每轮 = user + assistant，共最多 12 条
LLM_TIMEOUT = 90.0

SYSTEM_PROMPT = """你是外卖/门店销售数据看板的经营分析助手。

规则：
1. 只能依据工具返回的聚合数据回答；没有调用工具或工具无数据时，明确说明无法判断，不要臆造数字。
2. 用简洁的中文经营口吻：先给结论，再列关键数字依据；金额保留约 2 位小数或万元量级表述均可。
3. 当前问题对应的品牌、日期、平台、门店范围已由系统锁定，你无法也不应尝试改变筛选范围。
4. 禁止输出 SQL、数据库表名、连接信息、API Key 或内部实现细节。
5. 若用户问题超出工具能力（如单笔订单、顾客隐私），礼貌说明看板仅有聚合指标。
"""


def ai_ready() -> tuple[bool, str]:
    """配置是否可用；不可用时返回原因。"""
    if not AI_ENABLED:
        return False, "AI 分析未启用（AI_ENABLED=false）"
    if not AI_API_KEY:
        return False, "未配置 AI_API_KEY"
    if not AI_API_BASE:
        return False, "未配置 AI_API_BASE"
    return True, ""


def _sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps({"type": event, **data}, ensure_ascii=False)
    return f"data: {payload}\n\n"


def _brand_label(brand: str) -> str:
    return BRANDS.get(brand, {}).get("label") or brand


def _filter_hint(ctx: FilterContext) -> str:
    plats = "、".join(ctx.platforms) if ctx.platforms else "全部平台"
    stores = f"已选 {len(ctx.store_ids)} 个门店 ID" if ctx.store_ids else "全部门店"
    return (
        f"当前锁定范围：品牌={_brand_label(ctx.brand)}（{ctx.brand}），"
        f"日期={ctx.start.isoformat()}～{ctx.end.isoformat()}，平台={plats}，门店={stores}。"
    )


def _normalize_history(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """只保留 user/assistant 文本，截断轮数。"""
    if not history:
        return []
    cleaned: list[dict[str, str]] = []
    for item in history:
        role = (item.get("role") or "").strip()
        content = (item.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        cleaned.append({"role": role, "content": content})
    max_msgs = HISTORY_MAX_TURNS * 2
    return cleaned[-max_msgs:]


async def _chat_completion(
    client: httpx.AsyncClient,
    messages: list[dict[str, Any]],
    *,
    with_tools: bool,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": AI_MODEL,
        "messages": messages,
        "temperature": 0.3,
    }
    if with_tools:
        body["tools"] = TOOL_DEFINITIONS
        body["tool_choice"] = "auto"

    r = await client.post(
        f"{AI_API_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=LLM_TIMEOUT,
    )
    if r.status_code >= 400:
        detail = r.text[:500]
        logger.warning("LLM HTTP %s: %s", r.status_code, detail)
        raise RuntimeError(f"模型接口错误 HTTP {r.status_code}")
    return r.json()


async def run_chat(
    *,
    engine: Engine,
    ctx: FilterContext,
    message: str,
    history: list[dict[str, str]] | None,
    user_id: int,
) -> AsyncIterator[str]:
    """生成 SSE 字符串片段：status / token / done / error。

    数据库连接仅在执行工具时短暂占用，不跨 LLM 网络等待。
    """
    ok, reason = ai_ready()
    if not ok:
        yield _sse("error", {"message": reason})
        return

    msg = (message or "").strip()
    if not msg:
        yield _sse("error", {"message": "请输入问题"})
        return

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n" + _filter_hint(ctx)},
        *_normalize_history(history),
        {"role": "user", "content": msg},
    ]

    tools_used: list[str] = []
    t0 = time.perf_counter()

    try:
        async with httpx.AsyncClient() as client:
            for round_i in range(AI_MAX_TOOL_ROUNDS + 1):
                data = await _chat_completion(
                    client, messages, with_tools=round_i < AI_MAX_TOOL_ROUNDS,
                )
                choice = (data.get("choices") or [{}])[0]
                assistant_msg = choice.get("message") or {}
                tool_calls = assistant_msg.get("tool_calls") or []

                if tool_calls and round_i < AI_MAX_TOOL_ROUNDS:
                    messages.append({
                        "role": "assistant",
                        "content": assistant_msg.get("content") or None,
                        "tool_calls": tool_calls,
                    })
                    with engine.connect() as conn:
                        for tc in tool_calls:
                            fn = (tc.get("function") or {})
                            name = fn.get("name") or ""
                            tools_used.append(name)
                            label = TOOL_STATUS_LABELS.get(name, f"正在查询 {name}…")
                            yield _sse("status", {"message": label, "tool": name})
                            result = run_tool(name, conn, ctx)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc.get("id") or name,
                                "content": result,
                            })
                            logger.info(
                                "ai_tool user=%s brand=%s tool=%s ok",
                                user_id, ctx.brand, name,
                            )
                    continue

                content = (assistant_msg.get("content") or "").strip()
                if not content:
                    yield _sse("error", {"message": "模型未返回有效回答，请换个问法重试"})
                    return

                chunk_size = 24
                for i in range(0, len(content), chunk_size):
                    yield _sse("token", {"text": content[i : i + chunk_size]})

                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                logger.info(
                    "ai_chat user=%s brand=%s tools=%s ms=%s ok",
                    user_id, ctx.brand, tools_used, elapsed_ms,
                )
                yield _sse("done", {
                    "tools": tools_used,
                    "elapsed_ms": elapsed_ms,
                })
                return

            yield _sse("error", {"message": "工具调用轮次已达上限，请缩小问题范围后重试"})
    except httpx.TimeoutException:
        logger.warning("ai_chat timeout user=%s brand=%s", user_id, ctx.brand)
        yield _sse("error", {"message": "模型请求超时，请稍后重试"})
    except Exception as e:
        logger.exception("ai_chat failed user=%s brand=%s", user_id, ctx.brand)
        yield _sse("error", {"message": f"分析失败：{e}"})
