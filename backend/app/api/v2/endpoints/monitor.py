"""Monitor/alert endpoints for API v2."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core.contracts import ok
from app.core.errors import BadRequestError, NotFoundError, UpstreamError
from app.exchange import exchange_manager
from app.services.alert_service import alert_service
from app.services.strategy_service import strategy_service

router = APIRouter()


class AlertCreateRequest(BaseModel):
    name: str
    type: str
    exchange: str = "okx"
    symbol: str
    threshold: float
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    webhook_url: Optional[str] = None


@router.get("/alerts")
async def alerts():
    return ok(alert_service.get_alerts())


@router.post("/alerts")
async def create_alert(payload: AlertCreateRequest):
    condition = {
        "exchange": payload.exchange,
        "symbol": payload.symbol,
        "threshold": payload.threshold,
    }
    notification: Dict[str, Any] = {}
    if payload.telegram_bot_token and payload.telegram_chat_id:
        notification["telegram"] = {
            "bot_token": payload.telegram_bot_token,
            "chat_id": payload.telegram_chat_id,
        }
    if payload.webhook_url:
        notification["webhook"] = {"url": payload.webhook_url}

    alert_id = await alert_service.create_alert(
        name=payload.name,
        alert_type=payload.type,
        condition=condition,
        notification=notification,
    )
    return ok({"id": alert_id})


@router.put("/alerts/{alert_id}")
async def update_alert(alert_id: int, enabled: bool = Query(...)):
    exists = any(item.get("id") == alert_id for item in alert_service.get_alerts())
    if not exists:
        raise NotFoundError("Alert not found")
    await alert_service.toggle_alert(alert_id, enabled)
    return ok({"id": alert_id, "enabled": enabled})


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: int):
    exists = any(item.get("id") == alert_id for item in alert_service.get_alerts())
    if not exists:
        raise NotFoundError("Alert not found")
    await alert_service.delete_alert(alert_id)
    return ok({"deleted": True})


@router.get("/running-strategies")
async def running_strategies():
    return ok(await strategy_service.get_all_running())


@router.get("/long-short-ratio")
async def get_long_short_ratio(
    exchange: str = Query("okx", description="交易所"),
    symbol: str = Query("BTC/USDT:USDT", description="交易对"),
):
    ex = exchange_manager.get_exchange(exchange)
    if not ex:
        raise BadRequestError(f"Exchange {exchange} not supported")

    if exchange != "okx" or not hasattr(ex.exchange, "fapiPublicGetTopLongShortPositionRatio"):
        raise BadRequestError("Not supported for this exchange")

    try:
        await asyncio.to_thread(ex.load_markets)
        market = await asyncio.to_thread(ex.exchange.market, symbol)
        response = await asyncio.to_thread(
            ex.exchange.fapiPublicGetTopLongShortPositionRatio,
            {"symbol": market["id"], "period": "5m", "limit": 1},
        )
        if not response:
            raise UpstreamError("No data from exchange")
        item = response[0]
        return ok(
            {
                "exchange": exchange,
                "symbol": symbol,
                "long_ratio": float(item.get("longAccount", 0)),
                "short_ratio": float(item.get("shortAccount", 0)),
                "long_short_ratio": float(item.get("longShortRatio", 0)),
                "timestamp": int(item.get("timestamp", 0)),
            }
        )
    except Exception as exc:
        raise UpstreamError(f"获取多空比失败: {exc}") from exc


@router.get("/open-interest")
async def get_open_interest(
    exchange: str = Query("okx", description="交易所"),
    symbol: str = Query("BTC/USDT:USDT", description="交易对"),
):
    ex = exchange_manager.get_exchange(exchange)
    if not ex:
        raise BadRequestError(f"Exchange {exchange} not supported")

    if exchange != "okx" or not hasattr(ex.exchange, "fapiPublicGetOpenInterest"):
        raise BadRequestError("Not supported for this exchange")

    try:
        await asyncio.to_thread(ex.load_markets)
        market = await asyncio.to_thread(ex.exchange.market, symbol)
        response = await asyncio.to_thread(ex.exchange.fapiPublicGetOpenInterest, {"symbol": market["id"]})
        return ok(
            {
                "exchange": exchange,
                "symbol": symbol,
                "open_interest": float(response.get("openInterest", 0)),
                "timestamp": response.get("time"),
            }
        )
    except Exception as exc:
        raise UpstreamError(f"获取持仓量失败: {exc}") from exc
