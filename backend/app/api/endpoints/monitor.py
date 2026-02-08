"""
监控告警 API
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel
from app.services.alert_service import alert_service, AlertType
from app.exchange import exchange_manager

router = APIRouter()


class AlertCreateRequest(BaseModel):
    """创建告警请求"""
    name: str
    type: str  # price_above/price_below/price_change/funding_above/funding_below
    exchange: str = "okx"
    symbol: str
    threshold: float
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    webhook_url: Optional[str] = None


@router.get("/alerts")
async def get_alerts():
    """
    获取告警列表
    """
    return alert_service.get_alerts()


@router.post("/alert")
async def create_alert(request: AlertCreateRequest):
    """
    创建告警
    
    告警类型:
    - price_above: 价格高于阈值
    - price_below: 价格低于阈值
    - price_change: 价格变动超过阈值(%)
    - funding_above: 资金费率高于阈值
    - funding_below: 资金费率低于阈值
    """
    condition = {
        'exchange': request.exchange,
        'symbol': request.symbol,
        'threshold': request.threshold,
    }
    
    notification = {}
    if request.telegram_bot_token and request.telegram_chat_id:
        notification['telegram'] = {
            'bot_token': request.telegram_bot_token,
            'chat_id': request.telegram_chat_id,
        }
    if request.webhook_url:
        notification['webhook'] = {
            'url': request.webhook_url,
        }
    
    alert_id = await alert_service.create_alert(
        name=request.name,
        alert_type=request.type,
        condition=condition,
        notification=notification,
    )
    
    return {'id': alert_id, 'message': 'Alert created'}


@router.put("/alert/{alert_id}")
async def update_alert(alert_id: int, enabled: bool = Query(...)):
    """
    启用/禁用告警
    """
    await alert_service.toggle_alert(alert_id, enabled)
    return {'message': f'Alert {"enabled" if enabled else "disabled"}'}


@router.delete("/alert/{alert_id}")
async def delete_alert(alert_id: int):
    """
    删除告警
    """
    await alert_service.delete_alert(alert_id)
    return {'message': 'Alert deleted'}


@router.get("/running-strategies")
async def get_running_strategies():
    """
    获取运行中的策略
    """
    from app.services.strategy_service import strategy_service
    return await strategy_service.get_all_running()


@router.get("/liquidations")
async def get_liquidations(
    exchange: str = Query("okx", description="交易所"),
    symbol: Optional[str] = Query(None, description="交易对"),
    limit: int = Query(50, ge=1, le=200)
):
    """
    获取爆仓数据 (从数据库缓存)
    """
    from app.db.local_db import db_instance as db
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    if symbol:
        cursor.execute('''
            SELECT exchange, symbol, timestamp, side, price, quantity, value
            FROM liquidation_history
            WHERE exchange = ? AND symbol = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (exchange, symbol, limit))
    else:
        cursor.execute('''
            SELECT exchange, symbol, timestamp, side, price, quantity, value
            FROM liquidation_history
            WHERE exchange = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (exchange, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


@router.get("/long-short-ratio")
async def get_long_short_ratio(
    exchange_name: str = Query("okx", description="交易所"),
    symbol: str = Query("BTC/USDT:USDT", description="交易对")
):
    """
    获取多空比
    """
    exchange = exchange_manager.get_exchange(exchange_name)
    if not exchange:
        raise HTTPException(status_code=400, detail="Exchange not supported")
    
    # OKX 特有 API
    if exchange_name == 'okx' and hasattr(exchange.exchange, 'fapiPublicGetTopLongShortPositionRatio'):
        try:
            exchange.load_markets()
            market = exchange.exchange.market(symbol)
            response = exchange.exchange.fapiPublicGetTopLongShortPositionRatio({
                'symbol': market['id'],
                'period': '5m',
                'limit': 1
            })
            
            if response and len(response) > 0:
                item = response[0]
                return {
                    'exchange': exchange_name,
                    'symbol': symbol,
                    'long_ratio': float(item.get('longAccount', 0)),
                    'short_ratio': float(item.get('shortAccount', 0)),
                    'long_short_ratio': float(item.get('longShortRatio', 0)),
                    'timestamp': int(item.get('timestamp', 0))
                }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    raise HTTPException(status_code=501, detail="Not supported for this exchange")


@router.get("/open-interest")
async def get_open_interest(
    exchange_name: str = Query("okx", description="交易所"),
    symbol: str = Query("BTC/USDT:USDT", description="交易对")
):
    """
    获取持仓量
    """
    exchange = exchange_manager.get_exchange(exchange_name)
    if not exchange:
        raise HTTPException(status_code=400, detail="Exchange not supported")
    
    # OKX 特有 API
    if exchange_name == 'okx' and hasattr(exchange.exchange, 'fapiPublicGetOpenInterest'):
        try:
            exchange.load_markets()
            market = exchange.exchange.market(symbol)
            response = exchange.exchange.fapiPublicGetOpenInterest({
                'symbol': market['id']
            })
            
            return {
                'exchange': exchange_name,
                'symbol': symbol,
                'open_interest': float(response.get('openInterest', 0)),
                'timestamp': response.get('time')
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    raise HTTPException(status_code=501, detail="Not supported for this exchange")
