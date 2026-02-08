"""
行情数据 API
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.models.schemas import Ticker, Kline, OrderBook, Trade
from app.services.market_service import market_service

router = APIRouter()


@router.get("/ticker", response_model=Ticker)
async def get_ticker(
    exchange: str = Query(..., description="交易所: okx"),
    symbol: str = Query(..., description="交易对: BTC/USDT")
):
    """
    获取单个交易对实时行情
    """
    try:
        ticker = await market_service.get_ticker(exchange, symbol)
        return ticker
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tickers", response_model=List[Ticker])
async def get_tickers(
    exchange: str = Query(..., description="交易所"),
    symbols: Optional[str] = Query(None, description="交易对列表，逗号分隔")
):
    """
    获取多个交易对行情
    """
    try:
        symbol_list = symbols.split(",") if symbols else None
        tickers = await market_service.get_tickers(exchange, symbol_list)
        return tickers
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/klines", response_model=List[Kline])
async def get_klines(
    exchange: str = Query(..., description="交易所"),
    symbol: str = Query(..., description="交易对"),
    timeframe: str = Query("1h", description="周期: 1m/5m/15m/1h/4h/1d"),
    limit: int = Query(100, ge=1, le=1000, description="数量限制"),
    start: Optional[int] = Query(None, description="开始时间戳(毫秒)"),
    end: Optional[int] = Query(None, description="结束时间戳(毫秒)")
):
    """
    获取K线数据
    """
    try:
        klines = await market_service.get_klines(
            exchange, symbol, timeframe, limit, start, end
        )
        return klines
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orderbook", response_model=OrderBook)
async def get_orderbook(
    exchange: str = Query(..., description="交易所"),
    symbol: str = Query(..., description="交易对"),
    limit: int = Query(20, ge=1, le=100, description="深度档数")
):
    """
    获取订单簿深度
    """
    try:
        orderbook = await market_service.get_orderbook(exchange, symbol, limit)
        return orderbook
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades", response_model=List[Trade])
async def get_trades(
    exchange: str = Query(..., description="交易所"),
    symbol: str = Query(..., description="交易对"),
    limit: int = Query(50, ge=1, le=500, description="数量限制")
):
    """
    获取最近成交记录
    """
    try:
        trades = await market_service.get_trades(exchange, symbol, limit)
        return trades
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbols")
async def get_symbols(
    exchange: str = Query(..., description="交易所"),
    quote: Optional[str] = Query("USDT", description="计价币种")
):
    """
    获取交易对列表
    """
    try:
        symbols = await market_service.get_symbols(exchange, quote)
        return {"symbols": symbols}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
