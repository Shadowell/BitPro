"""
BitPro - 加密货币量化交易平台
主应用入口
"""
# 最先加载 .env，确保所有模块都能读到环境变量
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
import asyncio
import logging
import json
import re

from app.core.config import settings
from app.api import api_router
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
# 中间件：API 响应自动 snake_case -> camelCase
# 解决前后端字段命名不一致的问题
# ============================================

def _snake_to_camel(name: str) -> str:
    """snake_case -> camelCase"""
    components = name.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


def _convert_keys(obj):
    """递归转换字典键名为 camelCase"""
    if isinstance(obj, dict):
        return {_snake_to_camel(k): _convert_keys(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_keys(item) for item in obj]
    return obj


class CamelCaseResponseMiddleware(BaseHTTPMiddleware):
    """自动将 API JSON 响应的 snake_case 键名转为 camelCase"""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # 只处理 JSON 响应且是 API 请求
        if (response.headers.get('content-type', '').startswith('application/json')
                and request.url.path.startswith('/api/')):
            
            # 读取原始响应体
            body = b''
            async for chunk in response.body_iterator:
                body += chunk if isinstance(chunk, bytes) else chunk.encode()
            
            try:
                data = json.loads(body)
                camel_data = _convert_keys(data)
                new_body = json.dumps(camel_data, ensure_ascii=False)
                
                # 复制 headers 但移除 content-length（让 Response 自动计算）
                headers = {k: v for k, v in response.headers.items()
                           if k.lower() not in ('content-length', 'content-type')}
                
                return Response(
                    content=new_body,
                    status_code=response.status_code,
                    headers=headers,
                    media_type='application/json',
                )
            except (json.JSONDecodeError, Exception):
                # 转换失败，返回原始响应
                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.headers.get('content-type'),
                )
        
        return response


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
# 全局异常处理器
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

# API 响应自动 snake_case -> camelCase
app.add_middleware(CamelCaseResponseMiddleware)

# 请求限流
app.add_middleware(RateLimitMiddleware, global_rate=60, trade_rate=10)

# 注册路由
app.include_router(api_router, prefix=settings.API_V1_STR)


# 全局异常处理：避免 500 错误泄露内部实现细节
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """统一异常处理"""
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "服务器内部错误，请稍后重试",
            "error_code": "INTERNAL_ERROR",
        }
    )


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "欢迎使用 BitPro API",
        "docs": "/docs",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8889,
        reload=True
    )
