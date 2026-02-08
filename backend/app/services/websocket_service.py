"""
WebSocket 服务
实时数据推送: 行情、资金费率、订单更新等
"""
import asyncio
import json
import logging
from typing import Dict, Set, List, Optional, Any
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ChannelType(str, Enum):
    """订阅频道类型"""
    TICKER = "ticker"           # 单个交易对实时行情
    TICKERS = "tickers"         # 批量行情（首页用）
    KLINE = "kline"             # K线更新
    ORDERBOOK = "orderbook"     # 订单簿
    TRADES = "trades"           # 成交记录
    FUNDING = "funding"         # 资金费率
    LIQUIDATION = "liquidation" # 爆仓
    STRATEGY = "strategy"       # 策略状态


@dataclass
class Subscription:
    """订阅信息"""
    channel: ChannelType
    exchange: str
    symbol: Optional[str] = None
    params: Dict = field(default_factory=dict)


class ConnectionManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        # websocket -> subscriptions
        self.active_connections: Dict[WebSocket, Set[str]] = {}
        # subscription_key -> set of websockets
        self.subscriptions: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket):
        """新连接"""
        await websocket.accept()
        async with self._lock:
            self.active_connections[websocket] = set()
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")
    
    async def disconnect(self, websocket: WebSocket):
        """断开连接"""
        async with self._lock:
            # 清理订阅
            if websocket in self.active_connections:
                subs = self.active_connections.pop(websocket)
                for sub_key in subs:
                    if sub_key in self.subscriptions:
                        self.subscriptions[sub_key].discard(websocket)
                        if not self.subscriptions[sub_key]:
                            del self.subscriptions[sub_key]
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")
    
    async def subscribe(self, websocket: WebSocket, channel: str, 
                       exchange: str, symbol: str = None) -> str:
        """订阅频道"""
        sub_key = self._make_key(channel, exchange, symbol)
        
        async with self._lock:
            if websocket not in self.active_connections:
                return None
            
            self.active_connections[websocket].add(sub_key)
            
            if sub_key not in self.subscriptions:
                self.subscriptions[sub_key] = set()
            self.subscriptions[sub_key].add(websocket)
        
        logger.debug(f"Subscribed to {sub_key}")
        return sub_key
    
    async def unsubscribe(self, websocket: WebSocket, channel: str,
                         exchange: str, symbol: str = None) -> bool:
        """取消订阅"""
        sub_key = self._make_key(channel, exchange, symbol)
        
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections[websocket].discard(sub_key)
            
            if sub_key in self.subscriptions:
                self.subscriptions[sub_key].discard(websocket)
                if not self.subscriptions[sub_key]:
                    del self.subscriptions[sub_key]
        
        return True
    
    async def broadcast(self, channel: str, exchange: str, 
                       symbol: str, data: Dict):
        """广播数据到订阅者"""
        sub_key = self._make_key(channel, exchange, symbol)
        
        if sub_key not in self.subscriptions:
            return
        
        message = json.dumps({
            "channel": channel,
            "exchange": exchange,
            "symbol": symbol,
            "data": data,
            "timestamp": int(datetime.now().timestamp() * 1000)
        })
        
        dead_connections = []
        for websocket in self.subscriptions[sub_key]:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send message: {e}")
                dead_connections.append(websocket)
        
        # 清理失效连接
        for ws in dead_connections:
            await self.disconnect(ws)
    
    async def send_personal(self, websocket: WebSocket, data: Dict):
        """发送个人消息"""
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.warning(f"Failed to send personal message: {e}")
    
    def _make_key(self, channel: str, exchange: str, symbol: str = None) -> str:
        """生成订阅 key"""
        if symbol:
            return f"{channel}:{exchange}:{symbol}"
        return f"{channel}:{exchange}"
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "connections": len(self.active_connections),
            "subscriptions": {k: len(v) for k, v in self.subscriptions.items()}
        }


class RealtimeDataService:
    """实时数据服务"""
    
    def __init__(self, manager: ConnectionManager):
        self.manager = manager
        self._running = False
        self._tasks: List[asyncio.Task] = []
    
    async def start(self):
        """启动实时数据服务"""
        if self._running:
            return
        
        self._running = True
        
        # 启动各数据源任务
        self._tasks = [
            asyncio.create_task(self._ticker_loop()),
            asyncio.create_task(self._tickers_loop()),
            asyncio.create_task(self._funding_loop()),
        ]
        
        logger.info("Realtime data service started")
    
    async def stop(self):
        """停止服务"""
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks = []
        logger.info("Realtime data service stopped")
    
    async def _ticker_loop(self):
        """行情推送循环"""
        from app.exchange import exchange_manager
        
        while self._running:
            try:
                # 检查有哪些订阅
                ticker_subs = [k for k in self.manager.subscriptions.keys() 
                              if k.startswith("ticker:")]
                
                for sub_key in ticker_subs:
                    parts = sub_key.split(":")
                    if len(parts) < 3:
                        continue
                    
                    _, exchange_name, symbol = parts[0], parts[1], parts[2]
                    
                    try:
                        exchange = exchange_manager.get_exchange(exchange_name)
                        if exchange:
                            ticker = exchange.fetch_ticker(symbol)
                            await self.manager.broadcast(
                                "ticker", exchange_name, symbol, ticker
                            )
                    except Exception as e:
                        logger.warning(f"Failed to fetch ticker {symbol}: {e}")
                
                await asyncio.sleep(2)  # 2秒更新一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ticker loop error: {e}")
                await asyncio.sleep(5)
    
    async def _tickers_loop(self):
        """批量行情推送循环（首页用）
        
        订阅 key 格式: tickers:{exchange}
        前端订阅时不需要指定 symbol，后端会推送所有主流交易对的 ticker 数据
        """
        from app.exchange import exchange_manager
        
        # 主流交易对列表
        BATCH_SYMBOLS = [
            'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT',
            'DOGE/USDT', 'ADA/USDT', 'AVAX/USDT', 'DOT/USDT', 'LINK/USDT',
            'LTC/USDT', 'UNI/USDT', 'NEAR/USDT', 'APT/USDT', 'ARB/USDT',
            'OP/USDT', 'SUI/USDT', 'PEPE/USDT', 'FIL/USDT', 'ATOM/USDT',
            'INJ/USDT', 'FET/USDT', 'TIA/USDT', 'BCH/USDT', 'XLM/USDT',
            'WIF/USDT', 'RUNE/USDT', 'AAVE/USDT', 'MATIC/USDT', 'STX/USDT',
            'IMX/USDT', 'SEI/USDT',
        ]
        
        while self._running:
            try:
                tickers_subs = [k for k in self.manager.subscriptions.keys()
                               if k.startswith("tickers:")]
                
                for sub_key in tickers_subs:
                    parts = sub_key.split(":")
                    if len(parts) < 2:
                        continue
                    
                    exchange_name = parts[1]
                    
                    try:
                        exchange = exchange_manager.get_exchange(exchange_name)
                        if exchange:
                            all_tickers = exchange.fetch_tickers(BATCH_SYMBOLS)
                            if all_tickers:
                                await self.manager.broadcast(
                                    "tickers", exchange_name, "*", all_tickers
                                )
                    except Exception as e:
                        logger.warning(f"Failed to batch fetch tickers for {exchange_name}: {e}")
                
                await asyncio.sleep(3)  # 3秒批量更新一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Tickers loop error: {e}")
                await asyncio.sleep(5)

    async def _funding_loop(self):
        """资金费率推送循环"""
        from app.exchange import exchange_manager
        
        while self._running:
            try:
                funding_subs = [k for k in self.manager.subscriptions.keys()
                               if k.startswith("funding:")]
                
                for sub_key in funding_subs:
                    parts = sub_key.split(":")
                    if len(parts) < 2:
                        continue
                    
                    exchange_name = parts[1]
                    symbol = parts[2] if len(parts) > 2 else None
                    
                    try:
                        exchange = exchange_manager.get_exchange(exchange_name)
                        if exchange:
                            if symbol:
                                rate = exchange.fetch_funding_rate(symbol)
                                if rate:
                                    await self.manager.broadcast(
                                        "funding", exchange_name, symbol, rate
                                    )
                            else:
                                rates = exchange.fetch_funding_rates()
                                for rate in rates[:20]:  # 限制数量
                                    await self.manager.broadcast(
                                        "funding", exchange_name, 
                                        rate.get('symbol', ''), rate
                                    )
                    except Exception as e:
                        logger.warning(f"Failed to fetch funding: {e}")
                
                await asyncio.sleep(30)  # 30秒更新一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Funding loop error: {e}")
                await asyncio.sleep(60)


# 全局实例
connection_manager = ConnectionManager()
realtime_service = RealtimeDataService(connection_manager)
