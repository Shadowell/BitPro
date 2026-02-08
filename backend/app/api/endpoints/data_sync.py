"""
数据同步 API
手动触发同步、查看同步状态、查询可用数据、分表统计
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from typing import List, Optional
from pydantic import BaseModel

from app.services.data_sync_service import data_sync_service, DEFAULT_SYMBOLS, DEFAULT_TIMEFRAMES
from app.db.local_db import db_instance as db

router = APIRouter()


# ============================================
# 请求模型
# ============================================

class SyncRequest(BaseModel):
    """同步请求"""
    exchange: str = "okx"
    symbols: Optional[List[str]] = None
    timeframes: Optional[List[str]] = None
    history_days: int = 365  # 默认1年
    start_date: Optional[str] = None  # YYYY-MM-DD
    end_date: Optional[str] = None


class SyncSingleRequest(BaseModel):
    """单个交易对同步请求"""
    exchange: str = "okx"
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    history_days: int = 365


# ============================================
# API 端点
# ============================================

@router.post("/start")
async def start_sync(request: SyncRequest, background_tasks: BackgroundTasks):
    """
    启动批量数据同步（后台运行）
    
    同步指定交易所的多个交易对和时间周期的历史K线数据到本地数据库。
    """
    status = data_sync_service.get_sync_status()
    if status['is_running']:
        raise HTTPException(status_code=409, detail="已有同步任务在运行中")

    async def run_sync():
        await data_sync_service.sync_all(
            exchange_name=request.exchange,
            symbols=request.symbols,
            timeframes=request.timeframes,
            history_days=request.history_days,
            start_date=request.start_date,
            end_date=request.end_date,
        )

    background_tasks.add_task(run_sync)

    return {
        "message": "同步任务已启动",
        "exchange": request.exchange,
        "symbols": request.symbols or DEFAULT_SYMBOLS,
        "timeframes": request.timeframes or DEFAULT_TIMEFRAMES,
        "history_days": request.history_days,
    }


@router.post("/sync_one")
async def sync_single(request: SyncSingleRequest):
    """
    同步单个交易对（同步等待完成）
    
    适合手动补充某个交易对的数据。
    """
    status = data_sync_service.get_sync_status()
    if status['is_running']:
        raise HTTPException(status_code=409, detail="已有同步任务在运行中")

    result = await data_sync_service.sync_klines(
        exchange_name=request.exchange,
        symbol=request.symbol,
        timeframe=request.timeframe,
        start_date=request.start_date,
        end_date=request.end_date,
        history_days=request.history_days,
    )

    return {
        "exchange": result.exchange,
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "status": result.status.value,
        "total_fetched": result.total_fetched,
        "total_inserted": result.total_inserted,
        "error": result.error,
        "elapsed_seconds": (
            (result.end_time - result.start_time).total_seconds()
            if result.end_time and result.start_time else None
        ),
    }


@router.get("/status")
async def get_sync_status():
    """
    获取同步服务状态
    
    返回当前是否在运行、已同步的数据概况等。
    """
    return data_sync_service.get_sync_status()


@router.get("/data")
async def get_available_data(
    exchange: str = Query(None, description="交易所名称")
):
    """
    获取已同步的数据清单
    
    列出所有已同步到本地的交易对、时间周期、数据量和时间范围。
    """
    return data_sync_service.get_available_data(exchange)


@router.post("/daily_update")
async def trigger_daily_update(
    exchange: str = "okx",
    background_tasks: BackgroundTasks = None
):
    """
    手动触发每日增量更新
    
    适合在定时任务未触发时手动补数据。
    """
    status = data_sync_service.get_sync_status()
    if status['is_running']:
        raise HTTPException(status_code=409, detail="已有同步任务在运行中")

    async def run_update():
        await data_sync_service.daily_update(exchange)

    background_tasks.add_task(run_update)

    return {
        "message": "每日增量更新已启动",
        "exchange": exchange,
    }


@router.get("/config")
async def get_sync_config():
    """
    获取默认同步配置
    """
    return {
        "default_symbols": DEFAULT_SYMBOLS,
        "default_timeframes": DEFAULT_TIMEFRAMES,
        "default_history_days": 365,
    }


@router.get("/table_stats")
async def get_table_stats():
    """
    获取所有K线分表的统计信息
    返回每个表每个交易对的记录数、时间范围
    """
    stats = db.get_kline_table_stats()
    return {
        "tables": stats,
        "total_records": sum(s['record_count'] for s in stats),
        "total_pairs": len(set((s['exchange'], s['symbol'], s['timeframe']) for s in stats)),
    }


class DeleteDataRequest(BaseModel):
    """删除数据请求"""
    exchange: str = "okx"
    symbol: Optional[str] = None  # 不传则删除该交易所全部
    timeframe: Optional[str] = None  # 不传则删除该交易对全部周期


@router.post("/delete")
async def delete_kline_data(request: DeleteDataRequest):
    """
    删除指定交易对/周期的K线数据
    """
    conn = db.get_connection()
    cursor = conn.cursor()
    deleted_total = 0

    try:
        # 分表删除
        for tf in ['1m', '5m', '15m', '1h', '4h', '1d']:
            if request.timeframe and request.timeframe != tf:
                continue
            table = f'kline_{tf}'
            if request.symbol:
                cursor.execute(
                    f'DELETE FROM {table} WHERE exchange = ? AND symbol = ?',
                    (request.exchange, request.symbol)
                )
            else:
                cursor.execute(
                    f'DELETE FROM {table} WHERE exchange = ?',
                    (request.exchange,)
                )
            deleted_total += cursor.rowcount

        # 旧统一表删除
        if request.symbol and request.timeframe:
            cursor.execute(
                'DELETE FROM kline_history WHERE exchange = ? AND symbol = ? AND timeframe = ?',
                (request.exchange, request.symbol, request.timeframe)
            )
        elif request.symbol:
            cursor.execute(
                'DELETE FROM kline_history WHERE exchange = ? AND symbol = ?',
                (request.exchange, request.symbol)
            )
        else:
            cursor.execute(
                'DELETE FROM kline_history WHERE exchange = ?',
                (request.exchange,)
            )
        deleted_total += cursor.rowcount

        conn.commit()
    finally:
        conn.close()

    return {
        "message": f"已删除 {deleted_total} 条记录",
        "deleted": deleted_total,
    }
