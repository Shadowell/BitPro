"""Domain service for market data with non-blocking adapters."""
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

from app.core.errors import ExchangeUnavailableError, UpstreamError
from app.domain.market.repository import MarketRepository
from app.exchange import exchange_manager


class MarketDomainService:
    """Market domain service with strict upstream dependency behavior."""

    def __init__(self, repo: Optional[MarketRepository] = None):
        self.repo = repo or MarketRepository()

    def _get_exchange(self, exchange_name: str):
        exchange = exchange_manager.get_exchange(exchange_name)
        if not exchange:
            raise ExchangeUnavailableError(f"交易所 {exchange_name} 不可用")
        return exchange

    def _cache_tickers(self, exchange_name: str, tickers: List[Dict]) -> None:
        for ticker in tickers:
            symbol = ticker.get("symbol")
            if symbol:
                self.repo.update_ticker_cache(exchange_name, symbol, ticker)

    async def get_ticker(self, exchange_name: str, symbol: str) -> Dict:
        exchange = self._get_exchange(exchange_name)
        try:
            ticker = await asyncio.to_thread(exchange.fetch_ticker, symbol)
            await asyncio.to_thread(self.repo.update_ticker_cache, exchange_name, symbol, ticker)
            return ticker
        except Exception as exc:
            raise UpstreamError(f"获取行情失败: {exc}") from exc

    async def get_tickers(self, exchange_name: str, symbols: Optional[List[str]] = None) -> List[Dict]:
        exchange = self._get_exchange(exchange_name)
        try:
            tickers = await asyncio.to_thread(exchange.fetch_tickers, symbols)
            if isinstance(tickers, dict):
                normalized = list(tickers.values())
            else:
                normalized = tickers or []
            await asyncio.to_thread(self._cache_tickers, exchange_name, normalized)
            return normalized
        except Exception as exc:
            raise UpstreamError(f"批量获取行情失败: {exc}") from exc

    async def get_klines(
        self,
        exchange_name: str,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
        start: Optional[int] = None,
        end: Optional[int] = None,
    ) -> List[Dict]:
        exchange = self._get_exchange(exchange_name)

        cached = await asyncio.to_thread(
            self.repo.get_klines,
            exchange_name,
            symbol,
            timeframe,
            limit,
            start,
            end,
        )
        if len(cached) >= limit:
            return cached[:limit]

        try:
            klines = await asyncio.to_thread(exchange.fetch_ohlcv, symbol, timeframe, limit, start)
            if klines:
                await asyncio.to_thread(self.repo.insert_klines, exchange_name, symbol, timeframe, klines)
            return klines
        except Exception as exc:
            raise UpstreamError(f"获取K线失败: {exc}") from exc

    async def get_orderbook(self, exchange_name: str, symbol: str, limit: int = 20) -> Dict:
        exchange = self._get_exchange(exchange_name)
        valid_limits = [5, 10, 20, 50, 100, 500, 1000]
        adjusted_limit = min(v for v in valid_limits if v >= limit) if limit <= 1000 else 1000
        try:
            return await asyncio.to_thread(exchange.fetch_order_book, symbol, adjusted_limit)
        except Exception as exc:
            raise UpstreamError(f"获取订单簿失败: {exc}") from exc

    async def get_trades(self, exchange_name: str, symbol: str, limit: int = 50) -> List[Dict]:
        exchange = self._get_exchange(exchange_name)
        try:
            return await asyncio.to_thread(exchange.fetch_trades, symbol, limit)
        except Exception as exc:
            raise UpstreamError(f"获取成交失败: {exc}") from exc

    async def get_symbols(self, exchange_name: str, quote: str = "USDT") -> List[str]:
        exchange = self._get_exchange(exchange_name)
        try:
            return await asyncio.to_thread(exchange.get_symbols, quote)
        except Exception as exc:
            raise UpstreamError(f"获取交易对失败: {exc}") from exc


market_domain_service = MarketDomainService()
