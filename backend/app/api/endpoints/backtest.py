"""
回测 API — 基于 v2 回测引擎
==============================
所有回测均通过 strategy_registry 映射到 v2 引擎的纯函数策略，
不再使用 exec() 执行脚本。
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import asyncio
import json
import logging
import numpy as np

from app.db.local_db import db_instance as db
from app.services.strategy_backtest import Backtest, BacktestConfig as V2Config, BacktestResultV2
from app.services.strategy_registry import get_strategy_for_id, resolve_strategy, list_available_strategies

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================
# 请求 / 响应 模型
# ============================================

class BacktestRequest(BaseModel):
    """回测请求"""
    strategy_id: int
    exchange: str = "okx"
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    start_date: str
    end_date: str
    initial_capital: float = 10000
    commission: float = 0.0004
    slippage: float = 0.0001
    stop_loss: Optional[float] = None       # e.g. 0.05 = 5%
    take_profit: Optional[float] = None
    trailing_stop: Optional[float] = None


class BacktestResultResponse(BaseModel):
    """回测结果响应 — 前端使用"""
    strategy_id: int
    strategy_name: Optional[str] = None
    status: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float
    final_capital: Optional[float] = None
    total_return: Optional[float] = None
    annual_return: Optional[float] = None
    max_drawdown: Optional[float] = None
    max_drawdown_duration_days: Optional[int] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None
    total_trades: Optional[int] = None
    winning_trades: Optional[int] = None
    losing_trades: Optional[int] = None
    avg_win_pct: Optional[float] = None
    avg_loss_pct: Optional[float] = None
    max_consecutive_wins: Optional[int] = None
    max_consecutive_losses: Optional[int] = None
    expectancy: Optional[float] = None
    total_fees: Optional[float] = None
    avg_holding_bars: Optional[float] = None
    total_bars: Optional[int] = None
    elapsed_seconds: Optional[float] = None
    monthly_returns: Optional[Dict[str, float]] = None
    equity_curve: Optional[List[dict]] = None
    trades: Optional[List[dict]] = None
    error_message: Optional[str] = None


# ============================================
# 工具函数
# ============================================

def _safe_float(v) -> Optional[float]:
    """将 numpy 类型安全转为 Python float"""
    if v is None:
        return None
    if isinstance(v, (np.floating, np.integer)):
        val = float(v)
        if np.isnan(val) or np.isinf(val):
            return 0.0
        return val
    if isinstance(v, float):
        if np.isnan(v) or np.isinf(v):
            return 0.0
    return float(v)


def _v2_result_to_response(result: BacktestResultV2, strategy_id: int,
                            strategy_name: str = '') -> BacktestResultResponse:
    """将 v2 引擎结果转为前端响应格式"""

    # 构建 equity_curve (前端需要 [{timestamp, equity, drawdown}])
    equity_curve_list = []
    if len(result.equity_curve) > 0 and len(result.timestamps) > 0:
        # 计算回撤序列
        peak = result.equity_curve[0]
        for i in range(len(result.equity_curve)):
            eq = float(result.equity_curve[i])
            ts = int(result.timestamps[i])
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100 if peak > 0 else 0
            equity_curve_list.append({
                'timestamp': ts,
                'equity': round(eq, 2),
                'drawdown': round(dd, 2),
            })

    # 构建 trades
    trades_list = []
    for t in result.trades:
        trades_list.append({
            'timestamp': int(t.timestamp),
            'side': t.side,
            'price': round(float(t.price), 4),
            'quantity': round(float(t.quantity), 6),
            'pnl': round(float(t.pnl), 4),
            'pnl_pct': round(float(t.pnl_pct), 4),
            'fee': round(float(t.fee), 4),
            'reason': t.reason,
        })

    return BacktestResultResponse(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        status=result.status,
        start_date=result.config.start_date,
        end_date=result.config.end_date,
        initial_capital=_safe_float(result.initial_capital),
        final_capital=_safe_float(result.final_equity),
        total_return=_safe_float(result.total_return_pct),
        annual_return=_safe_float(result.annual_return_pct),
        max_drawdown=_safe_float(result.max_drawdown_pct),
        max_drawdown_duration_days=int(result.max_drawdown_duration_days),
        sharpe_ratio=_safe_float(result.sharpe_ratio),
        sortino_ratio=_safe_float(result.sortino_ratio),
        calmar_ratio=_safe_float(result.calmar_ratio),
        win_rate=_safe_float(result.win_rate_pct),
        profit_factor=_safe_float(result.profit_factor),
        total_trades=int(result.total_trades),
        winning_trades=int(result.winning_trades),
        losing_trades=int(result.losing_trades),
        avg_win_pct=_safe_float(result.avg_win_pct),
        avg_loss_pct=_safe_float(result.avg_loss_pct),
        max_consecutive_wins=int(result.max_consecutive_wins),
        max_consecutive_losses=int(result.max_consecutive_losses),
        expectancy=_safe_float(result.expectancy),
        total_fees=_safe_float(result.total_fees),
        avg_holding_bars=_safe_float(result.avg_holding_bars),
        total_bars=int(result.total_bars),
        elapsed_seconds=_safe_float(result.elapsed_seconds),
        monthly_returns=result.monthly_returns or None,
        equity_curve=equity_curve_list,
        trades=trades_list,
        error_message=result.error_message if result.status == 'failed' else None,
    )


def _save_result_to_db(result: BacktestResultV2, strategy_id: int, trades_list: List[dict]):
    """保存回测结果到数据库"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        trades_json = json.dumps(trades_list, ensure_ascii=False)

        cursor.execute('''
            INSERT INTO backtest_results
            (strategy_id, start_date, end_date, initial_capital, final_capital,
             total_return, annual_return, max_drawdown, sharpe_ratio, win_rate,
             profit_factor, total_trades, trades_detail, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            strategy_id,
            result.config.start_date,
            result.config.end_date,
            float(result.initial_capital),
            float(result.final_equity),
            float(result.total_return_pct),
            float(result.annual_return_pct),
            float(result.max_drawdown_pct),
            float(result.sharpe_ratio),
            float(result.win_rate_pct),
            float(result.profit_factor),
            int(result.total_trades),
            trades_json,
            result.status,
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"保存回测结果失败: {e}")


# ============================================
# API 端点
# ============================================

@router.post("/run_sync", response_model=BacktestResultResponse)
async def run_backtest_sync(request: BacktestRequest):
    """
    运行回测 (同步) — 使用 v2 引擎
    """
    # 1. 解析策略
    strategy_info = get_strategy_for_id(request.strategy_id)
    if not strategy_info:
        raise HTTPException(
            status_code=400,
            detail=f"策略 #{request.strategy_id} 无法映射到 v2 回测引擎。"
                   f"请确保该策略已在 strategy_registry 中注册。"
        )

    strategy_fn = strategy_info['fn']
    setup_fn = strategy_info.get('setup')
    strategy_name = strategy_info.get('name', '')

    # 2. 构建 v2 配置
    # 如果用户没有指定止损，使用策略的默认止损
    stop_loss = request.stop_loss
    if stop_loss is None:
        stop_loss = strategy_info.get('stop_loss')

    config = V2Config(
        exchange=request.exchange,
        symbol=request.symbol,
        timeframe=request.timeframe,
        start_date=request.start_date,
        end_date=request.end_date,
        initial_capital=request.initial_capital,
        commission=request.commission,
        slippage=request.slippage,
        stop_loss=stop_loss,
        take_profit=request.take_profit,
        trailing_stop=request.trailing_stop,
    )

    # 3. 运行 v2 回测 (可能需要从交易所拉取数据，放到线程池避免阻塞)
    bt = Backtest(config, strategy_fn, setup_fn)
    result = await asyncio.to_thread(bt.run)

    # 4. 转为响应格式
    response = _v2_result_to_response(result, request.strategy_id, strategy_name)

    # 5. 保存结果到数据库
    if result.status == 'completed':
        _save_result_to_db(result, request.strategy_id, response.trades or [])

    return response


@router.post("/run")
async def run_backtest(request: BacktestRequest):
    """
    运行回测 (异步) — 实际上 v2 引擎很快，直接同步返回
    """
    return await run_backtest_sync(request)


@router.get("/strategies")
async def get_available_strategies():
    """获取所有可用于回测的 v2 策略列表"""
    return list_available_strategies()


@router.get("/status/{strategy_id}")
async def get_backtest_status(strategy_id: int):
    """获取回测状态 (兼容旧接口)"""
    return {"strategy_id": strategy_id, "status": "completed", "message": "v2引擎为同步执行"}


@router.get("/results")
async def get_backtest_results(
    strategy_id: int = Query(None, description="策略ID"),
    limit: int = Query(20, ge=1, le=100)
):
    """获取回测结果列表 (从数据库)"""
    conn = db.get_connection()
    cursor = conn.cursor()

    if strategy_id:
        cursor.execute('''
            SELECT id, strategy_id, start_date, end_date, initial_capital, final_capital,
                   total_return, annual_return, max_drawdown, sharpe_ratio, win_rate,
                   profit_factor, total_trades, status, created_at
            FROM backtest_results
            WHERE strategy_id = ?
            ORDER BY created_at DESC LIMIT ?
        ''', (strategy_id, limit))
    else:
        cursor.execute('''
            SELECT id, strategy_id, start_date, end_date, initial_capital, final_capital,
                   total_return, annual_return, max_drawdown, sharpe_ratio, win_rate,
                   profit_factor, total_trades, status, created_at
            FROM backtest_results
            ORDER BY created_at DESC LIMIT ?
        ''', (limit,))

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


@router.get("/result/{backtest_id}")
async def get_backtest_result(backtest_id: int):
    """获取回测结果详情"""
    conn = db.get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, strategy_id, start_date, end_date, initial_capital, final_capital,
               total_return, annual_return, max_drawdown, sharpe_ratio, win_rate,
               profit_factor, total_trades, trades_detail, status, created_at
        FROM backtest_results WHERE id = ?
    ''', (backtest_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Backtest result not found")

    result = dict(row)
    if result.get('trades_detail'):
        result['trades'] = json.loads(result['trades_detail'])
        del result['trades_detail']

    return result
