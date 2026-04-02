"""
BitPro - 加密货币量化交易平台
主应用入口
"""
# 最先加载 .env，确保所有模块都能读到环境变量
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
import logging

from app.core.config import settings
from app.api import api_router, api_router_v2
from app.core.errors import register_exception_handlers
from app.db.local_db import db_instance as db

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("Starting BitPro application...")
    
    # 初始化数据库
    db.init_db()
    logger.info("Database initialized")
    
    # 初始化交易所连接
    from app.exchange import exchange_manager
    exchange_manager.init_exchanges()
    logger.info("Exchange connections initialized")
    
    # 启动 WebSocket 实时数据服务
    from app.services.websocket_service import realtime_service
    await realtime_service.start()
    logger.info("WebSocket realtime service started")
    
    # 启动策略执行引擎
    from app.services.strategy_engine import strategy_engine
    await strategy_engine.start()
    logger.info("Strategy engine started")
    
    # 启动告警服务
    from app.services.alert_service import alert_service
    await alert_service.start()
    logger.info("Alert service started")
    
    # 启动定时调度服务（每日数据同步等）
    from app.services.scheduler_service import scheduler_service
    await scheduler_service.start()
    logger.info("Scheduler service started")
    
    yield
    
    # 关闭时
    logger.info("Shutting down BitPro application...")
    
    # 停止定时调度服务
    await scheduler_service.stop()
    
    # 停止告警服务
    await alert_service.stop()
    
    # 停止策略引擎
    await strategy_engine.stop()
    
    # 停止实时数据服务
    await realtime_service.stop()


# ============================================
# 请求限流中间件
# 保护交易所 API 不被前端频繁请求打穿
# ============================================

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    简易令牌桶限流
    - 全局: 60 请求/秒
    - 交易接口: 10 请求/秒
    """
    
    def __init__(self, app, global_rate: int = 60, trade_rate: int = 10):
        super().__init__(app)
        self._global_tokens = global_rate
        self._global_max = global_rate
        self._trade_tokens = trade_rate
        self._trade_max = trade_rate
        self._last_refill = 0.0
    
    async def dispatch(self, request: Request, call_next):
        import time
        now = time.time()
        
        # 令牌补充 (每秒补满) — 单进程下无需加锁，asyncio 是单线程的
        elapsed = now - self._last_refill
        if elapsed >= 1.0:
            self._global_tokens = self._global_max
            self._trade_tokens = self._trade_max
            self._last_refill = now
        
        path = request.url.path
        
        # 交易接口限流
        if '/trading/' in path or '/auto-trade/' in path or '/live/' in path:
            if self._trade_tokens <= 0:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "交易接口请求频率过高，请稍后再试"}
                )
            self._trade_tokens -= 1
        
        # 全局限流
        if path.startswith('/api/'):
            if self._global_tokens <= 0:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "请求频率过高，请稍后再试"}
                )
            self._global_tokens -= 1
        
        return await call_next(request)


# ============================================
# 应用注册
# ============================================

# 创建应用
app = FastAPI(
    title="BitPro API",
    description="加密货币量化交易平台 API",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求限流
app.add_middleware(RateLimitMiddleware, global_rate=60, trade_rate=10)

# 注册路由
app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(api_router_v2, prefix="/api/v2")

# 注册全局异常处理
register_exception_handlers(app)


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "欢迎使用 BitPro API",
        "docs": "/docs",
        "version": "2.0.0",
        "v1": settings.API_V1_STR,
        "v2": "/api/v2",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8889,
        reload=True
    )
