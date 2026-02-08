"""
模拟盘交易 API
Phase 4: Paper Trading + 风控 + 压力测试
"""
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import Optional, List
from pydantic import BaseModel
import logging

from app.services.paper_trading import PaperTradingEngine, RiskConfig, stress_test
from app.services.signal_notifier import signal_notifier, pre_flight_checklist

router = APIRouter()
logger = logging.getLogger(__name__)

# 全局模拟盘引擎实例
_engines = {}

def _resolve_paper_strategy(strategy_input: str) -> str:
    """将策略标识解析为 PaperTradingEngine 支持的策略名"""
    from app.db.local_db import db_instance as db

    # 尝试解析为数据库 ID
    raw = strategy_input.replace('db_', '') if strategy_input.startswith('db_') else strategy_input
    try:
        db_id = int(raw)
        strategy = db.get_strategy_by_id(db_id)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"策略 #{db_id} 不存在")

        cfg = strategy.get('config') or {}
        key = cfg.get('strategy_key', '')

        # 实盘版策略映射到回测版 (PaperTradingEngine 只认不带 _live 的 key)
        paper_key = key.replace('_live', '')
        logger.info(f"模拟盘: 策略 '{strategy['name']}' → '{paper_key}'")
        return paper_key if paper_key else 'adaptive_bollinger'
    except ValueError:
        pass

    return strategy_input.replace('_live', '')


class PaperTradingRequest(BaseModel):
    """模拟盘请求"""
    strategy: str = "adaptive_bollinger"
    exchange: str = "okx"
    symbol: str = "BTC/USDT"
    timeframe: str = "4h"
    initial_capital: float = 10000.0
    stop_loss: float = 0.05
    days_back: int = 90

    # 风控参数
    account_stop_loss: float = 0.15
    daily_stop_loss: float = 0.05
    consecutive_loss_limit: int = 5
    volatility_circuit_breaker: float = 0.08


class StressTestRequest(BaseModel):
    """压力测试请求"""
    strategy: str = "adaptive_bollinger"
    symbol: str = "BTC/USDT"
    timeframe: str = "4h"
    scenarios: List[str] = ["full_period", "recent_90d", "recent_30d"]


@router.post("/run")
async def run_paper_trading(request: PaperTradingRequest):
    """
    运行模拟盘
    用最近N天的数据模拟实盘交易过程（含风控）
    """
    try:
        # 解析策略名称 — 支持数据库ID和直接key
        strategy_name = _resolve_paper_strategy(request.strategy)

        risk_config = RiskConfig(
            account_stop_loss=request.account_stop_loss,
            daily_stop_loss=request.daily_stop_loss,
            consecutive_loss_limit=request.consecutive_loss_limit,
            volatility_circuit_breaker=request.volatility_circuit_breaker,
        )

        engine = PaperTradingEngine(
            strategy_name=strategy_name,
            exchange=request.exchange,
            symbol=request.symbol,
            timeframe=request.timeframe,
            initial_capital=request.initial_capital,
            stop_loss=request.stop_loss,
            risk_config=risk_config,
        )

        result = engine.run_simulation(days_back=request.days_back)

        # 保存引擎用于后续查询
        key = f"{request.strategy}_{request.symbol}_{request.timeframe}"
        _engines[key] = engine

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"模拟盘失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_paper_trading_status(
    strategy: str = Query("adaptive_bollinger"),
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("4h"),
):
    """获取模拟盘状态"""
    key = f"{strategy}_{symbol}_{timeframe}"
    engine = _engines.get(key)
    if not engine:
        return {"status": "not_started", "message": "模拟盘未启动，请先调用 POST /run"}
    return engine.status


@router.get("/signals")
async def get_signals(
    strategy: str = Query("adaptive_bollinger"),
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("4h"),
    limit: int = Query(100, ge=1, le=500),
):
    """获取信号记录"""
    key = f"{strategy}_{symbol}_{timeframe}"
    engine = _engines.get(key)
    if not engine:
        return []

    signals = engine.signals[-limit:]
    return [
        {
            'time': s.timestamp,
            'action': s.action,
            'reason': s.reason,
            'price': s.price,
            'quantity': s.quantity,
            'regime': s.regime,
            'rsi': s.rsi,
            'atr_pct': s.atr_pct,
            'equity': s.equity,
            'pnl': s.pnl,
        }
        for s in signals
    ]


@router.post("/stress_test")
async def run_stress_test(request: StressTestRequest):
    """
    压力测试
    在多个历史区间上验证策略的稳健性
    """
    try:
        results = stress_test(
            strategy_name=request.strategy,
            symbol=request.symbol,
            timeframe=request.timeframe,
            scenarios=request.scenarios,
        )

        # 汇总
        summary = {}
        for scenario, r in results.items():
            if r.get('status') == 'completed':
                summary[scenario] = {
                    'return_pct': r['total_return_pct'],
                    'max_drawdown_pct': r['max_drawdown_pct'],
                    'sharpe_ratio': r['sharpe_ratio'],
                    'total_trades': r['total_trades'],
                    'win_rate_pct': r['win_rate_pct'],
                    'risk_events': r['risk_events'],
                }
            else:
                summary[scenario] = {'status': r.get('status', 'error'), 'message': r.get('message', '')}

        return {
            'strategy': request.strategy,
            'symbol': request.symbol,
            'scenarios': summary,
            'details': results,
        }

    except Exception as e:
        logger.error(f"压力测试失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies")
async def get_available_strategies():
    """获取可用的模拟盘策略列表"""
    return {
        'strategies': [
            {
                'id': 'adaptive_bollinger',
                'name': '自适应布林带策略 (Phase3最优)',
                'description': '根据市场状态动态调参，Walk-Forward一致性75%，BTC 4h夏普1.35',
                'recommended': True,
            },
            {
                'id': 'trend_following',
                'name': '趋势跟踪策略',
                'description': 'EMA多头排列+突破入场，BTC/SOL效果优秀，夏普1.03',
                'recommended': False,
            },
            {
                'id': 'combo',
                'name': '多策略组合引擎',
                'description': '综合趋势和均值回归信号，研究阶段',
                'recommended': False,
            },
        ]
    }


@router.get("/risk_config")
async def get_default_risk_config():
    """获取默认风控配置"""
    rc = RiskConfig()
    return {
        'account_stop_loss': rc.account_stop_loss,
        'daily_stop_loss': rc.daily_stop_loss,
        'max_loss_per_trade': rc.max_loss_per_trade,
        'max_position_pct': rc.max_position_pct,
        'consecutive_loss_limit': rc.consecutive_loss_limit,
        'volatility_circuit_breaker': rc.volatility_circuit_breaker,
        'max_open_positions': rc.max_open_positions,
        'cooldown_minutes': rc.cooldown_minutes,
        'description': {
            'account_stop_loss': '账户级止损: 总亏损超过此比例立即停止所有交易 (不可恢复)',
            'daily_stop_loss': '单日止损: 当日亏损超过此比例暂停交易到次日',
            'max_loss_per_trade': '单笔最大亏损比例',
            'consecutive_loss_limit': '连续亏损次数达到此值后触发熔断',
            'volatility_circuit_breaker': '当ATR/价格比超过此值暂停交易',
        }
    }


@router.get("/live_signals")
async def get_live_signals(limit: int = Query(50, ge=1, le=500)):
    """获取实盘信号记录"""
    return signal_notifier.get_recent_signals(limit)


@router.get("/signal_stats")
async def get_signal_stats():
    """获取信号统计"""
    return signal_notifier.get_signal_stats()


class PreFlightRequest(BaseModel):
    """飞行检查请求"""
    strategy: str = "adaptive_bollinger"
    symbol: str = "BTC/USDT"
    timeframe: str = "4h"
    capital_pct: float = 0.10
    total_capital: float = 10000.0


@router.post("/pre_flight")
async def run_pre_flight_check(request: PreFlightRequest):
    """
    实盘前飞行检查 (Pre-Flight Checklist)
    在正式实盘前，必须通过所有检查项
    """
    try:
        result = pre_flight_checklist(
            strategy_name=request.strategy,
            symbol=request.symbol,
            timeframe=request.timeframe,
            capital_pct=request.capital_pct,
            total_capital=request.total_capital,
        )
        return result
    except Exception as e:
        logger.error(f"飞行检查失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
