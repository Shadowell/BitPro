"""
模拟盘交易 API
支持多实例并行：每次启动一个策略 → 生成独立实例 → 可同时运行多个
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict
from pydantic import BaseModel
import logging
import time
import uuid

from app.services.paper_trading import PaperTradingEngine, RiskConfig, stress_test
from app.services.signal_notifier import signal_notifier, pre_flight_checklist

router = APIRouter()
logger = logging.getLogger(__name__)

# ============================================
# 多实例管理
# ============================================

# 全局实例池: { instance_id: { engine, config, result, created_at, status } }
_instances: Dict[str, dict] = {}


def _resolve_paper_strategy(strategy_input: str) -> tuple:
    """
    将策略标识解析为 PaperTradingEngine 支持的策略名。
    返回 (strategy_key, strategy_name, strategy_db_id)
    """
    from app.db.local_db import db_instance as db

    raw = strategy_input.replace('db_', '') if strategy_input.startswith('db_') else strategy_input
    try:
        db_id = int(raw)
        strategy = db.get_strategy_by_id(db_id)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"策略 #{db_id} 不存在")

        cfg = strategy.get('config') or {}
        key = cfg.get('strategy_key', '')
        paper_key = key.replace('_live', '')
        name = strategy.get('name', paper_key)
        logger.info(f"模拟盘: 策略 '{name}' (ID={db_id}) → '{paper_key}'")
        return paper_key if paper_key else 'adaptive_bollinger', name, db_id
    except ValueError:
        pass

    clean = strategy_input.replace('_live', '')
    return clean, clean, None


# ============================================
# 请求模型
# ============================================

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


class PreFlightRequest(BaseModel):
    """飞行检查请求"""
    strategy: str = "adaptive_bollinger"
    symbol: str = "BTC/USDT"
    timeframe: str = "4h"
    capital_pct: float = 0.10
    total_capital: float = 10000.0


# ============================================
# 核心端点
# ============================================

@router.post("/run")
async def run_paper_trading(request: PaperTradingRequest):
    """
    启动一个模拟盘实例。
    返回结果中包含 instance_id，可用于后续查询/停止。
    """
    try:
        strategy_key, strategy_name, db_id = _resolve_paper_strategy(request.strategy)

        risk_config = RiskConfig(
            account_stop_loss=request.account_stop_loss,
            daily_stop_loss=request.daily_stop_loss,
            consecutive_loss_limit=request.consecutive_loss_limit,
            volatility_circuit_breaker=request.volatility_circuit_breaker,
        )

        engine = PaperTradingEngine(
            strategy_name=strategy_key,
            exchange=request.exchange,
            symbol=request.symbol,
            timeframe=request.timeframe,
            initial_capital=request.initial_capital,
            stop_loss=request.stop_loss,
            risk_config=risk_config,
        )

        result = engine.run_simulation(days_back=request.days_back)

        # 生成唯一实例ID
        instance_id = f"paper_{int(time.time())}_{uuid.uuid4().hex[:6]}"

        # 保存到实例池
        _instances[instance_id] = {
            'engine': engine,
            'result': result,
            'config': {
                'strategy': request.strategy,
                'strategy_key': strategy_key,
                'strategy_name': strategy_name,
                'strategy_db_id': db_id,
                'exchange': request.exchange,
                'symbol': request.symbol,
                'timeframe': request.timeframe,
                'initial_capital': request.initial_capital,
                'days_back': request.days_back,
            },
            'created_at': time.time(),
            'status': 'completed',
        }

        # 注入 instance_id 到结果
        if isinstance(result, dict):
            result['instance_id'] = instance_id
            result['strategy_name'] = strategy_name
            result['strategy_db_id'] = db_id
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"模拟盘失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/instances")
async def list_instances():
    """列出所有模拟盘实例"""
    items = []
    for iid, inst in _instances.items():
        cfg = inst['config']
        result = inst.get('result') or {}

        # 兼容 snake_case 和 camelCase
        total_return = result.get('total_return_pct', result.get('totalReturnPct', 0))
        sharpe = result.get('sharpe_ratio', result.get('sharpeRatio', 0))
        max_dd = result.get('max_drawdown_pct', result.get('maxDrawdownPct', 0))
        total_trades = result.get('total_trades', result.get('totalTrades', 0))
        win_rate = result.get('win_rate_pct', result.get('winRatePct', 0))

        items.append({
            'instance_id': iid,
            'strategy_name': cfg.get('strategy_name', cfg.get('strategy_key', '?')),
            'strategy_db_id': cfg.get('strategy_db_id'),
            'symbol': cfg['symbol'],
            'timeframe': cfg['timeframe'],
            'initial_capital': cfg['initial_capital'],
            'days_back': cfg['days_back'],
            'status': inst['status'],
            'created_at': inst['created_at'],
            'total_return_pct': total_return,
            'sharpe_ratio': sharpe,
            'max_drawdown_pct': max_dd,
            'total_trades': total_trades,
            'win_rate_pct': win_rate,
        })

    # 按创建时间倒序
    items.sort(key=lambda x: x['created_at'], reverse=True)
    return {'instances': items, 'total': len(items)}


@router.get("/instances/{instance_id}")
async def get_instance_detail(instance_id: str):
    """获取模拟盘实例详情"""
    inst = _instances.get(instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail=f"实例 {instance_id} 不存在")

    return {
        'instance_id': instance_id,
        'config': inst['config'],
        'result': inst.get('result'),
        'status': inst['status'],
        'created_at': inst['created_at'],
    }


@router.delete("/instances/{instance_id}")
async def delete_instance(instance_id: str):
    """删除模拟盘实例"""
    if instance_id not in _instances:
        raise HTTPException(status_code=404, detail=f"实例 {instance_id} 不存在")

    del _instances[instance_id]
    return {'message': f'实例 {instance_id} 已删除', 'remaining': len(_instances)}


@router.delete("/instances")
async def clear_all_instances():
    """清空所有模拟盘实例"""
    count = len(_instances)
    _instances.clear()
    return {'message': f'已清空 {count} 个实例'}


# ============================================
# 信号查询 (兼容旧版 + 新版实例ID)
# ============================================

@router.get("/signals")
async def get_signals(
    instance_id: Optional[str] = Query(None),
    strategy: str = Query("adaptive_bollinger"),
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("4h"),
    limit: int = Query(100, ge=1, le=500),
):
    """获取信号记录（支持 instance_id 或旧版参数）"""
    engine = None

    if instance_id:
        inst = _instances.get(instance_id)
        if inst:
            engine = inst.get('engine')
    else:
        # 旧版兼容：按参数查找
        for inst in _instances.values():
            cfg = inst['config']
            if (cfg.get('strategy_key') == strategy and
                cfg['symbol'] == symbol and cfg['timeframe'] == timeframe):
                engine = inst.get('engine')
                break

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


# ============================================
# 压力测试 & 风控配置 & 飞行检查 & 信号统计
# ============================================

@router.post("/stress_test")
async def run_stress_test(request: StressTestRequest):
    """压力测试"""
    try:
        results = stress_test(
            strategy_name=request.strategy,
            symbol=request.symbol,
            timeframe=request.timeframe,
            scenarios=request.scenarios,
        )
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
        return {'strategy': request.strategy, 'symbol': request.symbol, 'scenarios': summary, 'details': results}
    except Exception as e:
        logger.error(f"压力测试失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
    }


@router.get("/live_signals")
async def get_live_signals(limit: int = Query(50, ge=1, le=500)):
    """获取实盘信号记录"""
    return signal_notifier.get_recent_signals(limit)


@router.get("/signal_stats")
async def get_signal_stats():
    """获取信号统计"""
    return signal_notifier.get_signal_stats()


@router.post("/pre_flight")
async def run_pre_flight_check(request: PreFlightRequest):
    """实盘前飞行检查"""
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
