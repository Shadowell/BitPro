"""API v2 router aggregation."""
from fastapi import APIRouter

from app.api.endpoints import backtest, live_trading, paper_trading, agent, data_sync
from app.api.v2.endpoints import system, market, funding, trading, strategy, sync, websocket, monitor

api_router_v2 = APIRouter()

# Core domain endpoints (v2)
api_router_v2.include_router(system.router, prefix="/system", tags=["System v2"])
api_router_v2.include_router(market.router, prefix="/market", tags=["Market v2"])
api_router_v2.include_router(funding.router, prefix="/funding", tags=["Funding v2"])
api_router_v2.include_router(trading.router, prefix="/trading", tags=["Trading v2"])
api_router_v2.include_router(strategy.router, prefix="/strategies", tags=["Strategy v2"])
api_router_v2.include_router(sync.router, prefix="/sync", tags=["Sync v2"])
api_router_v2.include_router(monitor.router, prefix="/monitor", tags=["Monitor v2"])
api_router_v2.include_router(websocket.router, tags=["WebSocket v2"])

# Legacy-compatible advanced domains temporarily mounted under v2 namespace
api_router_v2.include_router(backtest.router, prefix="/backtest", tags=["Backtest v2"])
api_router_v2.include_router(data_sync.router, prefix="/data_sync", tags=["Data Sync v2"])
api_router_v2.include_router(live_trading.router, prefix="/live", tags=["Live Trading v2"])
api_router_v2.include_router(paper_trading.router, prefix="/paper-trading", tags=["Paper Trading v2"])
api_router_v2.include_router(agent.router, prefix="/agent", tags=["Agent v2"])
