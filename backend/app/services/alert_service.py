"""
告警服务
支持价格、资金费率、持仓量等告警
支持 Telegram 通知
"""
import asyncio
import httpx
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import json
import logging

from app.db.local_db import db_instance as db
from app.exchange import exchange_manager
from app.core.config import settings

logger = logging.getLogger(__name__)


class AlertType(str, Enum):
    """告警类型"""
    PRICE_ABOVE = "price_above"       # 价格高于
    PRICE_BELOW = "price_below"       # 价格低于
    PRICE_CHANGE = "price_change"     # 价格变动%
    FUNDING_ABOVE = "funding_above"   # 费率高于
    FUNDING_BELOW = "funding_below"   # 费率低于
    VOLUME_SPIKE = "volume_spike"     # 成交量异常
    LIQUIDATION = "liquidation"       # 大额爆仓


class NotificationType(str, Enum):
    """通知方式"""
    TELEGRAM = "telegram"
    WEBHOOK = "webhook"
    EMAIL = "email"  # 暂不实现


@dataclass
class Alert:
    """告警配置"""
    id: int
    name: str
    type: AlertType
    exchange: str
    symbol: str
    condition: Dict[str, Any]
    notification: Dict[str, Any]
    enabled: bool = True
    last_triggered_at: Optional[datetime] = None
    cooldown: int = 300  # 冷却时间(秒)


@dataclass
class AlertEvent:
    """告警事件"""
    alert_id: int
    alert_name: str
    type: str
    symbol: str
    message: str
    value: float
    timestamp: datetime = field(default_factory=datetime.now)


class TelegramNotifier:
    """Telegram 通知器"""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
    
    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """发送消息"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "parse_mode": parse_mode
                    },
                    timeout=10
                )
                
                if response.status_code == 200:
                    logger.info(f"Telegram message sent to {self.chat_id}")
                    return True
                else:
                    logger.error(f"Telegram error: {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    async def send_alert(self, event: AlertEvent) -> bool:
        """发送告警"""
        # 格式化消息
        emoji = "🚨" if "price" in event.type else "📊"
        
        message = f"""
{emoji} <b>BitPro 告警</b>

<b>名称:</b> {event.alert_name}
<b>类型:</b> {event.type}
<b>交易对:</b> {event.symbol}
<b>当前值:</b> {event.value}
<b>时间:</b> {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}

{event.message}
"""
        return await self.send_message(message.strip())


class WebhookNotifier:
    """Webhook 通知器"""
    
    def __init__(self, url: str, headers: Dict[str, str] = None):
        self.url = url
        self.headers = headers or {}
    
    async def send_alert(self, event: AlertEvent) -> bool:
        """发送告警"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.url,
                    json={
                        "alert_id": event.alert_id,
                        "alert_name": event.alert_name,
                        "type": event.type,
                        "symbol": event.symbol,
                        "value": event.value,
                        "message": event.message,
                        "timestamp": event.timestamp.isoformat()
                    },
                    headers=self.headers,
                    timeout=10
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return False


class AlertService:
    """告警服务"""
    
    def __init__(self):
        self._alerts: Dict[int, Alert] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._telegram: Optional[TelegramNotifier] = None
        self._last_prices: Dict[str, float] = {}
    
    def init_telegram(self, bot_token: str, chat_id: str):
        """初始化 Telegram"""
        self._telegram = TelegramNotifier(bot_token, chat_id)
        logger.info("Telegram notifier initialized")
    
    async def start(self):
        """启动告警服务"""
        if self._running:
            return
        
        self._running = True
        
        # 加载告警配置
        await self._load_alerts()
        
        # 启动监控任务
        self._task = asyncio.create_task(self._monitor_loop())
        
        logger.info("Alert service started")
    
    async def stop(self):
        """停止告警服务"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Alert service stopped")
    
    async def _load_alerts(self):
        """从数据库加载告警配置"""
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, name, type, symbol, condition, notification, enabled, last_triggered_at
            FROM alerts
            WHERE enabled = 1
        ''')
        
        for row in cursor.fetchall():
            try:
                condition = json.loads(row['condition']) if row['condition'] else {}
                notification = json.loads(row['notification']) if row['notification'] else {}
                
                alert = Alert(
                    id=row['id'],
                    name=row['name'],
                    type=AlertType(row['type']),
                    exchange=condition.get('exchange', 'okx'),
                    symbol=condition.get('symbol', 'BTC/USDT'),
                    condition=condition,
                    notification=notification,
                    enabled=bool(row['enabled']),
                )
                self._alerts[alert.id] = alert
                
            except Exception as e:
                logger.warning(f"Failed to load alert {row['id']}: {e}")
        
        conn.close()
        logger.info(f"Loaded {len(self._alerts)} alerts")
    
    async def create_alert(self, name: str, alert_type: str, condition: Dict,
                          notification: Dict = None) -> int:
        """创建告警"""
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO alerts (name, type, symbol, condition, notification, enabled)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (
            name,
            alert_type,
            condition.get('symbol'),
            json.dumps(condition),
            json.dumps(notification or {})
        ))
        
        alert_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # 添加到内存
        alert = Alert(
            id=alert_id,
            name=name,
            type=AlertType(alert_type),
            exchange=condition.get('exchange', 'okx'),
            symbol=condition.get('symbol', 'BTC/USDT'),
            condition=condition,
            notification=notification or {},
        )
        self._alerts[alert_id] = alert
        
        logger.info(f"Alert created: {name} ({alert_type})")
        return alert_id
    
    async def delete_alert(self, alert_id: int) -> bool:
        """删除告警"""
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM alerts WHERE id = ?', (alert_id,))
        conn.commit()
        conn.close()
        
        self._alerts.pop(alert_id, None)
        return True
    
    async def toggle_alert(self, alert_id: int, enabled: bool) -> bool:
        """启用/禁用告警"""
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE alerts SET enabled = ? WHERE id = ?', (int(enabled), alert_id))
        conn.commit()
        conn.close()
        
        if alert_id in self._alerts:
            self._alerts[alert_id].enabled = enabled
        
        return True
    
    def get_alerts(self) -> List[Dict]:
        """获取所有告警"""
        return [
            {
                'id': a.id,
                'name': a.name,
                'type': a.type.value,
                'exchange': a.exchange,
                'symbol': a.symbol,
                'condition': a.condition,
                'enabled': a.enabled,
                'last_triggered_at': a.last_triggered_at.isoformat() if a.last_triggered_at else None,
            }
            for a in self._alerts.values()
        ]
    
    async def _monitor_loop(self):
        """监控循环"""
        while self._running:
            try:
                for alert in list(self._alerts.values()):
                    if not alert.enabled:
                        continue
                    
                    # 检查冷却
                    if alert.last_triggered_at:
                        elapsed = (datetime.now() - alert.last_triggered_at).total_seconds()
                        if elapsed < alert.cooldown:
                            continue
                    
                    # 检查告警条件
                    event = await self._check_alert(alert)
                    
                    if event:
                        await self._trigger_alert(alert, event)
                
                await asyncio.sleep(10)  # 10秒检查一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Alert monitor error: {e}")
                await asyncio.sleep(30)
    
    async def _check_alert(self, alert: Alert) -> Optional[AlertEvent]:
        """检查告警条件"""
        try:
            exchange = exchange_manager.get_exchange(alert.exchange)
            if not exchange:
                return None
            
            if alert.type in [AlertType.PRICE_ABOVE, AlertType.PRICE_BELOW, AlertType.PRICE_CHANGE]:
                return await self._check_price_alert(alert, exchange)
            
            elif alert.type in [AlertType.FUNDING_ABOVE, AlertType.FUNDING_BELOW]:
                return await self._check_funding_alert(alert, exchange)
            
            elif alert.type == AlertType.VOLUME_SPIKE:
                return await self._check_volume_alert(alert, exchange)
            
        except Exception as e:
            logger.warning(f"Alert check failed for {alert.name}: {e}")
        
        return None
    
    async def _check_price_alert(self, alert: Alert, exchange) -> Optional[AlertEvent]:
        """检查价格告警"""
        ticker = exchange.fetch_ticker(alert.symbol)
        current_price = ticker.get('last', 0)
        
        threshold = alert.condition.get('threshold', 0)
        
        if alert.type == AlertType.PRICE_ABOVE and current_price >= threshold:
            return AlertEvent(
                alert_id=alert.id,
                alert_name=alert.name,
                type=alert.type.value,
                symbol=alert.symbol,
                value=current_price,
                message=f"{alert.symbol} 价格突破 ${threshold}，当前 ${current_price:.2f}"
            )
        
        elif alert.type == AlertType.PRICE_BELOW and current_price <= threshold:
            return AlertEvent(
                alert_id=alert.id,
                alert_name=alert.name,
                type=alert.type.value,
                symbol=alert.symbol,
                value=current_price,
                message=f"{alert.symbol} 价格跌破 ${threshold}，当前 ${current_price:.2f}"
            )
        
        elif alert.type == AlertType.PRICE_CHANGE:
            key = f"{alert.exchange}:{alert.symbol}"
            last_price = self._last_prices.get(key)
            self._last_prices[key] = current_price
            
            if last_price:
                change = (current_price - last_price) / last_price * 100
                if abs(change) >= threshold:
                    direction = "上涨" if change > 0 else "下跌"
                    return AlertEvent(
                        alert_id=alert.id,
                        alert_name=alert.name,
                        type=alert.type.value,
                        symbol=alert.symbol,
                        value=change,
                        message=f"{alert.symbol} 价格快速{direction} {abs(change):.2f}%"
                    )
        
        return None
    
    async def _check_funding_alert(self, alert: Alert, exchange) -> Optional[AlertEvent]:
        """检查资金费率告警"""
        rate_data = exchange.fetch_funding_rate(alert.symbol)
        if not rate_data:
            return None
        
        current_rate = rate_data.get('current_rate', 0) or 0
        threshold = alert.condition.get('threshold', 0)
        
        if alert.type == AlertType.FUNDING_ABOVE and current_rate >= threshold:
            return AlertEvent(
                alert_id=alert.id,
                alert_name=alert.name,
                type=alert.type.value,
                symbol=alert.symbol,
                value=current_rate,
                message=f"{alert.symbol} 资金费率达到 {current_rate:.4%}，套利机会!"
            )
        
        elif alert.type == AlertType.FUNDING_BELOW and current_rate <= threshold:
            return AlertEvent(
                alert_id=alert.id,
                alert_name=alert.name,
                type=alert.type.value,
                symbol=alert.symbol,
                value=current_rate,
                message=f"{alert.symbol} 资金费率为 {current_rate:.4%}，低于阈值"
            )
        
        return None
    
    async def _check_volume_alert(self, alert: Alert, exchange) -> Optional[AlertEvent]:
        """检查成交量告警"""
        ticker = exchange.fetch_ticker(alert.symbol)
        volume = ticker.get('quoteVolume', 0) or ticker.get('baseVolume', 0) or 0
        
        threshold = alert.condition.get('threshold', 0)  # 24h成交额阈值
        
        if volume >= threshold:
            return AlertEvent(
                alert_id=alert.id,
                alert_name=alert.name,
                type=alert.type.value,
                symbol=alert.symbol,
                value=volume,
                message=f"{alert.symbol} 24h成交额达到 ${volume/1e6:.1f}M"
            )
        
        return None
    
    async def _trigger_alert(self, alert: Alert, event: AlertEvent):
        """触发告警"""
        logger.info(f"Alert triggered: {event.alert_name} - {event.message}")
        
        # 更新触发时间
        alert.last_triggered_at = datetime.now()
        
        # 发送通知
        notification = alert.notification
        
        if notification.get('telegram'):
            if self._telegram:
                await self._telegram.send_alert(event)
            else:
                # 使用配置的 Telegram
                tg_config = notification['telegram']
                if tg_config.get('bot_token') and tg_config.get('chat_id'):
                    notifier = TelegramNotifier(
                        tg_config['bot_token'],
                        tg_config['chat_id']
                    )
                    await notifier.send_alert(event)
        
        if notification.get('webhook'):
            webhook = WebhookNotifier(
                notification['webhook'].get('url'),
                notification['webhook'].get('headers')
            )
            await webhook.send_alert(event)
        
        # 更新数据库
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE alerts SET last_triggered_at = ? WHERE id = ?',
            (datetime.now().isoformat(), alert.id)
        )
        conn.commit()
        conn.close()


# 全局实例
alert_service = AlertService()
