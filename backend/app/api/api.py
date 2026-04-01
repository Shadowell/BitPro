"""
API 路由聚合
"""
from fastapi import APIRouter
from app.api.endpoints import market, funding, trading, strategy, backtest, monitor, health, websocket, data_sync, auto_trade, paper_trading, live_trading, agent

api_router = APIRouter()

# 健康检查
api_router.include_router(health.router, prefix="/health", tags=["健康检查"])

# 行情数据
api_router.include_router(market.router, prefix="/market", tags=["行情数据"])

# 资金费率
api_router.include_router(funding.router, prefix="/funding", tags=["资金费率"])

# 交易
api_router.include_router(trading.router, prefix="/trading", tags=["交易"])

# 策略
api_router.include_router(strategy.router, prefix="/strategy", tags=["策略"])

# 回测
api_router.include_router(backtest.router, prefix="/backtest", tags=["回测"])

# 监控告警
api_router.include_router(monitor.router, prefix="/monitor", tags=["监控告警"])

# 数据同步
api_router.include_router(data_sync.router, prefix="/data_sync", tags=["数据同步"])

# 自动化交易系统 (Pro)
api_router.include_router(auto_trade.router, prefix="/auto-trade", tags=["自动化交易"])

# 模拟盘交易 (Paper Trading)
api_router.include_router(paper_trading.router, prefix="/paper_trading", tags=["模拟盘交易"])

# 实盘交易系统 (Phase 5)
api_router.include_router(live_trading.router, prefix="/live", tags=["实盘交易"])

# AI Agent 系统
api_router.include_router(agent.router, prefix="/agent", tags=["AI Agent"])

# WebSocket
api_router.include_router(websocket.router, tags=["WebSocket"])
