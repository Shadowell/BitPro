"""
自动化交易 API
提供自动交易系统的配置、启停、监控接口
"""
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from app.services.auto_trader import (
    auto_trader, api_configure, api_start, api_stop, 
    api_status, api_strategies, api_analyze
)
from app.services.pro_backtest import (
    pro_backtest_engine, ProBacktestConfig,
    get_all_pro_backtests, get_pro_backtest_detail,
    get_pro_backtest_equity, get_latest_by_strategy,
)

router = APIRouter()


# ============================================
# 请求模型
# ============================================

class AutoTradeConfig(BaseModel):
    """自动交易配置"""
    exchange: str = "okx"
    strategy_type: str = "smart_trend"
    symbol: str = "BTC/USDT:USDT"
    timeframe: str = "1h"
    initial_equity: float = 100
    strategy_config: Optional[Dict[str, Any]] = None
    risk_config: Optional[Dict[str, Any]] = None
    higher_timeframe: str = ""
    loop_interval: int = 30
    dry_run: bool = True


# ============================================
# 系统控制
# ============================================

@router.post("/configure")
async def configure(config: AutoTradeConfig):
    """
    配置自动交易系统
    
    参数说明:
    - **exchange**: 交易所 (okx)
    - **strategy_type**: 策略类型
      - smart_trend: 智能趋势跟踪
      - mean_reversion: 均值回归
      - momentum_breakout: 动量突破
      - multi_timeframe: 多时间框架
      - funding_rate_pro: 资金费率增强版
      - scalping: 高频剥头皮
    - **symbol**: 交易对 (如 BTC/USDT:USDT)
    - **timeframe**: K线周期 (1m/5m/15m/1h/4h/1d)
    - **initial_equity**: 初始资金(USDT)
    - **dry_run**: true=模拟模式(不下单), false=实盘模式
    """
    result = await api_configure(config.dict())
    if result['status'] == 'error':
        raise HTTPException(status_code=400, detail=result['message'])
    return result


@router.post("/start")
async def start():
    """启动自动交易"""
    result = await api_start()
    if result['status'] == 'error':
        raise HTTPException(status_code=400, detail=result['message'])
    return result


@router.post("/stop")
async def stop():
    """停止自动交易"""
    result = await api_stop()
    if result['status'] == 'error':
        raise HTTPException(status_code=400, detail=result['message'])
    return result


@router.post("/pause")
async def pause():
    """暂停自动交易"""
    await auto_trader.pause()
    return {"status": "ok", "message": "系统已暂停"}


@router.post("/resume")
async def resume():
    """恢复自动交易"""
    await auto_trader.resume()
    return {"status": "ok", "message": "系统已恢复"}


# ============================================
# 状态查询
# ============================================

@router.get("/status")
async def get_status():
    """
    获取自动交易系统完整状态
    
    返回:
    - state: 系统状态 (idle/running/paused/stopped/error/circuit_breaker)
    - equity: 资金信息 (初始/当前/峰值/变化)
    - performance: 性能指标 (PnL/胜率/回撤等)
    - risk: 风控状态 (熔断/仓位/止损等)
    - recent_events: 最近事件列表
    """
    return await api_status()


@router.get("/events")
async def get_events(
    limit: int = Query(50, ge=1, le=200),
    event_type: Optional[str] = Query(None, description="事件类型: signal/order/close/error/system")
):
    """获取交易事件列表"""
    return auto_trader.get_events(limit, event_type)


@router.get("/equity-curve")
async def get_equity_curve():
    """获取权益曲线数据"""
    return auto_trader.get_equity_curve()


@router.get("/strategy-info")
async def get_strategy_info():
    """获取当前策略详情"""
    return auto_trader.get_strategy_info()


# ============================================
# 策略列表
# ============================================

@router.get("/strategies")
async def list_strategies():
    """
    列出所有可用的交易策略
    
    返回每个策略的名称、描述、风险等级、适用场景
    """
    return await api_strategies()


@router.get("/strategies/{strategy_type}")
async def get_strategy_detail(strategy_type: str):
    """获取策略详情"""
    detail = auto_trader.get_strategy_detail(strategy_type)
    if 'error' in detail:
        raise HTTPException(status_code=404, detail=detail['error'])
    return detail


# ============================================
# 技术分析
# ============================================

@router.get("/analyze")
async def analyze_market(
    exchange: str = Query("okx", description="交易所"),
    symbol: str = Query("BTC/USDT:USDT", description="交易对"),
    timeframe: str = Query("1h", description="K线周期")
):
    """
    实时技术分析
    
    对指定交易对进行全面的技术指标分析，返回:
    - overall_signal: 综合信号 (strong_buy/buy/neutral/sell/strong_sell)
    - score: 综合评分 (-1 到 +1)
    - indicators: 各指标数值 (RSI/MACD/BB/ADX等)
    - signals: 各指标信号详情
    """
    result = await api_analyze(exchange, symbol, timeframe)
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    return result


# ============================================
# 风控管理
# ============================================

@router.post("/risk/reset-circuit-breaker")
async def reset_circuit_breaker():
    """手动解除风控熔断"""
    if auto_trader._strategy:
        auto_trader._strategy.risk_manager.reset_circuit_breaker()
        return {"status": "ok", "message": "熔断已解除"}
    return {"status": "error", "message": "系统未配置"}


@router.post("/risk/reset-daily")
async def reset_daily_stats():
    """重置每日统计"""
    if auto_trader._strategy:
        auto_trader._strategy.risk_manager.reset_daily()
        return {"status": "ok", "message": "每日统计已重置"}
    return {"status": "error", "message": "系统未配置"}


# ============================================
# Pro 策略回测
# ============================================

class ProBacktestRequest(BaseModel):
    """Pro 策略回测请求"""
    strategy_type: str = "smart_trend"
    exchange: str = "okx"
    symbol: str = "BTC/USDT"
    timeframe: str = "4h"
    start_date: str = "2024-06-01"
    end_date: str = "2026-02-07"
    initial_capital: float = 10000
    commission: float = 0.0004
    slippage: float = 0.0001
    strategy_config: Dict = {}
    risk_config: Dict = {}
    higher_timeframe: str = ""


class ProBacktestAllRequest(BaseModel):
    """批量回测所有策略请求"""
    exchange: str = "okx"
    symbol: str = "BTC/USDT"
    timeframe: str = "4h"
    start_date: str = "2024-06-01"
    end_date: str = "2026-02-07"
    initial_capital: float = 10000


@router.post("/backtest/run")
async def run_pro_backtest(req: ProBacktestRequest):
    """运行单个 Pro 策略回测"""
    cfg = ProBacktestConfig(
        strategy_type=req.strategy_type,
        exchange=req.exchange,
        symbol=req.symbol,
        timeframe=req.timeframe,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=req.initial_capital,
        commission=req.commission,
        slippage=req.slippage,
        strategy_config=req.strategy_config,
        risk_config=req.risk_config,
        higher_timeframe=req.higher_timeframe,
    )
    try:
        result = await pro_backtest_engine.run(cfg)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backtest/run-all")
async def run_all_pro_backtests(req: ProBacktestAllRequest):
    """批量回测所有 Pro 策略"""
    try:
        results = await pro_backtest_engine.run_all(
            exchange=req.exchange,
            symbol=req.symbol,
            timeframe=req.timeframe,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_capital=req.initial_capital,
        )
        return {"count": len(results), "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backtest/results")
async def list_pro_backtests(limit: int = Query(50, ge=1, le=200)):
    """获取所有回测结果列表"""
    return get_all_pro_backtests(limit)


@router.get("/backtest/compare")
async def compare_strategies():
    """策略对比：每个策略取最新一次回测"""
    return get_latest_by_strategy()


@router.get("/backtest/results/{backtest_id}")
async def get_backtest_detail(backtest_id: int):
    """获取回测详情（含交易明细）"""
    detail = get_pro_backtest_detail(backtest_id)
    if not detail:
        raise HTTPException(status_code=404, detail="回测记录不存在")
    return detail


@router.get("/backtest/equity/{backtest_id}")
async def get_backtest_equity(backtest_id: int):
    """获取回测权益曲线"""
    equity = get_pro_backtest_equity(backtest_id)
    if not equity:
        raise HTTPException(status_code=404, detail="权益数据不存在")
    return equity
