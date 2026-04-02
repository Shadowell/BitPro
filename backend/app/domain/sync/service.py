"""Data sync domain service."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.db.local_db import db_instance as db
from app.services.data_sync_service import data_sync_service, DEFAULT_SYMBOLS, DEFAULT_TIMEFRAMES


class SyncDomainService:
    def status(self) -> Dict[str, Any]:
        return data_sync_service.get_sync_status()

    def config(self) -> Dict[str, Any]:
        return {
            "default_symbols": DEFAULT_SYMBOLS,
            "default_timeframes": DEFAULT_TIMEFRAMES,
            "default_history_days": 365,
        }

    def available_data(self, exchange: Optional[str] = None) -> List[Dict]:
        return data_sync_service.get_available_data(exchange)

    async def start(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await data_sync_service.sync_all(
            exchange_name=payload.get("exchange") or "okx",
            symbols=payload.get("symbols"),
            timeframes=payload.get("timeframes"),
            history_days=payload.get("history_days") or 365,
            start_date=payload.get("start_date"),
            end_date=payload.get("end_date"),
        )

    async def sync_one(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        progress = await data_sync_service.sync_klines(
            exchange_name=payload.get("exchange") or "okx",
            symbol=payload["symbol"],
            timeframe=payload["timeframe"],
            start_date=payload.get("start_date"),
            end_date=payload.get("end_date"),
            history_days=payload.get("history_days") or 365,
        )
        return {
            "exchange": progress.exchange,
            "symbol": progress.symbol,
            "timeframe": progress.timeframe,
            "status": progress.status.value,
            "total_fetched": progress.total_fetched,
            "total_inserted": progress.total_inserted,
            "error": progress.error,
        }

    def table_stats(self) -> Dict[str, Any]:
        stats = db.get_kline_table_stats()
        return {
            "tables": stats,
            "total_records": sum(s["record_count"] for s in stats),
            "total_pairs": len(set((s["exchange"], s["symbol"], s["timeframe"]) for s in stats)),
        }


sync_domain_service = SyncDomainService()
