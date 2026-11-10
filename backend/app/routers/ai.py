"""AI 自由问答：鉴权 + 品牌授权 + 限流 + SSE。"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import date
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import AI_RATE_LIMIT_PER_MIN, get_brand
from ..database import business_engine, get_app_db
from ..deps import authorize_brand, get_current_user
from ..models import User
from ..services import stores as store_svc
from ..services.ai_chat import ai_ready, run_chat
from ..services.ai_tools import FilterContext

router = APIRouter(prefix="/ai", tags=["ai"])

# 进程内滑动窗口限流：user_id -> 请求时间戳队列
_rate_lock = Lock()
_rate_hits: dict[int, deque[float]] = defaultdict(deque)


class ChatHistoryItem(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    brand: str
    start: date
    end: date
    platforms: list[str] | None = None
    store_ids: list[str] | None = None
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatHistoryItem] | None = None


def _check_rate_limit(user_id: int) -> None:
    now = time.monotonic()
    window = 60.0
    limit = max(1, AI_RATE_LIMIT_PER_MIN)
    with _rate_lock:
        q = _rate_hits[user_id]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, f"提问过于频繁，请稍后再试（每分钟最多 {limit} 次）")
        q.append(now)


@router.get("/status")
def ai_status(user: User = Depends(get_current_user)):
    """前端可据此决定是否展示 AI 入口。"""
    ok, reason = ai_ready()
    return {"enabled": ok, "reason": None if ok else reason}


@router.post("/chat")
async def ai_chat(
    body: ChatIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_app_db),
):
    ok, reason = ai_ready()
    if not ok:
        raise HTTPException(503, reason)

    if not get_brand(body.brand):
        raise HTTPException(400, f"未知品牌: {body.brand}")
    if body.end < body.start:
        raise HTTPException(400, "结束日期不能早于开始日期")

    authorize_brand(user, body.brand)
    _check_rate_limit(user.id)

    store_ids = store_svc.resolve_effective_store_ids(db, body.brand, body.store_ids)
    ctx = FilterContext(
        brand=body.brand,
        start=body.start,
        end=body.end,
        platforms=body.platforms or None,
        store_ids=store_ids,
    )
    history = [{"role": h.role, "content": h.content} for h in (body.history or [])]

    async def event_stream():
        async for chunk in run_chat(
            engine=business_engine,
            ctx=ctx,
            message=body.message,
            history=history,
            user_id=user.id,
        ):
            yield chunk

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
