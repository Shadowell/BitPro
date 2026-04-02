"""Market endpoints for API v2."""
from typing import Optional

from fastapi import APIRouter, Query

from app.core.contracts import ok, page_meta
from app.domain.market import market_domain_service

router = APIRouter()


@router.get("/ticker")
async def get_ticker(
    exchange: str = Query(..., description="交易所"),
    symbol: str = Query(..., description="交易对"),
):
    return ok(await market_domain_service.get_ticker(exchange, symbol))


@router.get("/tickers")
async def get_tickers(
    exchange: str = Query(..., description="交易所"),
    symbols: Optional[str] = Query(None, description="逗号分隔交易对"),
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
):
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
    items = await market_domain_service.get_tickers(exchange, symbol_list)
    total = len(items)
    paged = items[offset: offset + limit]
    return ok(paged, meta=page_meta(total=total, offset=offset, limit=limit))


@router.get("/klines")
async def get_klines(
    exchange: str = Query(..., description="交易所"),
    symbol: str = Query(..., description="交易对"),
    timeframe: str = Query("1h", description="周期"),
    limit: int = Query(100, ge=1, le=1000),
    start: Optional[int] = Query(None, description="开始时间戳(毫秒)"),
    end: Optional[int] = Query(None, description="结束时间戳(毫秒)"),
):
    return ok(await market_domain_service.get_klines(exchange, symbol, timeframe, limit, start, end))


@router.get("/orderbook")
async def get_orderbook(
    exchange: str = Query(..., description="交易所"),
    symbol: str = Query(..., description="交易对"),
    limit: int = Query(20, ge=1, le=1000),
):
    return ok(await market_domain_service.get_orderbook(exchange, symbol, limit))


@router.get("/trades")
async def get_trades(
    exchange: str = Query(..., description="交易所"),
    symbol: str = Query(..., description="交易对"),
    limit: int = Query(50, ge=1, le=500),
):
    return ok(await market_domain_service.get_trades(exchange, symbol, limit))


@router.get("/symbols")
async def get_symbols(
    exchange: str = Query(..., description="交易所"),
    quote: str = Query("USDT", description="计价币种"),
):
    symbols = await market_domain_service.get_symbols(exchange, quote)
    return ok({"symbols": symbols})
