"""
交易 API
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel
from app.services.trading_service import trading_service

router = APIRouter()


# ============================================
# 请求/响应模型
# ============================================

class SpotOrderRequest(BaseModel):
    """现货下单请求"""
    exchange: str = "okx"
    symbol: str  # 如 BTC/USDT
    side: str  # buy/sell
    type: str = "market"  # market/limit
    amount: float
    price: Optional[float] = None


class FuturesOrderRequest(BaseModel):
    """合约下单请求"""
    exchange: str = "okx"
    symbol: str  # 如 BTC/USDT:USDT
    side: str  # long/short
    action: str  # open/close
    amount: float
    leverage: int = 1
    price: Optional[float] = None


class CancelOrderRequest(BaseModel):
    """撤单请求"""
    exchange: str
    order_id: str
    symbol: str


class TransferRequest(BaseModel):
    """资金划转请求"""
    exchange: str = "okx"
    currency: str = "USDT"
    amount: float
    from_account: str = "funding"   # funding / trading
    to_account: str = "trading"     # funding / trading


# ============================================
# 账户接口
# ============================================

@router.get("/balance")
async def get_balance(
    exchange: str = Query("okx", description="交易所")
):
    """
    获取账户余额（合并所有子账户）
    """
    try:
        balance = await trading_service.get_balance(exchange)
        return {"exchange": exchange, "balance": balance}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/balance/detail")
async def get_balance_detail(
    exchange: str = Query("okx", description="交易所")
):
    """
    获取分账户余额（trading / funding 分别列出）
    """
    try:
        detail = await trading_service.get_balance_detail(exchange)
        return {"exchange": exchange, **detail}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transfer")
async def transfer_funds(request: TransferRequest):
    """
    资金划转：在 funding（资金账户）和 trading（交易账户）之间转账
    """
    try:
        result = await trading_service.transfer(
            request.exchange, request.currency, request.amount,
            request.from_account, request.to_account
        )
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def get_positions(
    exchange: str = Query("okx", description="交易所"),
    symbol: Optional[str] = Query(None, description="交易对")
):
    """
    获取持仓
    """
    try:
        positions = await trading_service.get_positions(exchange, symbol)
        return {"exchange": exchange, "positions": positions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 现货交易
# ============================================

@router.post("/spot/order")
async def spot_order(request: SpotOrderRequest):
    """
    现货下单
    
    - **symbol**: 交易对，如 BTC/USDT
    - **side**: buy 或 sell
    - **type**: market (市价) 或 limit (限价)
    - **amount**: 数量
    - **price**: 限价单价格 (市价单可不填)
    """
    try:
        # 风险检查
        risk = await trading_service.check_order_risk(
            request.exchange, request.symbol, request.side, 
            request.amount, request.price
        )
        
        if not risk['can_trade']:
            raise HTTPException(status_code=400, detail={
                "message": "Order rejected",
                "errors": risk['errors']
            })
        
        # 执行下单
        if request.type == "market":
            if request.side == "buy":
                order = await trading_service.spot_market_buy(
                    request.exchange, request.symbol, request.amount
                )
            else:
                order = await trading_service.spot_market_sell(
                    request.exchange, request.symbol, request.amount
                )
        else:  # limit
            if not request.price:
                raise HTTPException(status_code=400, detail="Price required for limit order")
            
            if request.side == "buy":
                order = await trading_service.spot_limit_buy(
                    request.exchange, request.symbol, request.amount, request.price
                )
            else:
                order = await trading_service.spot_limit_sell(
                    request.exchange, request.symbol, request.amount, request.price
                )
        
        return {
            "success": True,
            "order": order,
            "warnings": risk.get('warnings', [])
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 合约交易
# ============================================

@router.post("/futures/order")
async def futures_order(request: FuturesOrderRequest):
    """
    合约下单
    
    - **symbol**: 交易对，如 BTC/USDT:USDT
    - **side**: long (做多) 或 short (做空)
    - **action**: open (开仓) 或 close (平仓)
    - **amount**: 数量
    - **leverage**: 杠杆倍数 (开仓时有效)
    - **price**: 限价 (可选，不填则市价)
    """
    try:
        if request.action == "open":
            if request.side == "long":
                order = await trading_service.futures_open_long(
                    request.exchange, request.symbol, request.amount,
                    request.leverage, request.price
                )
            else:  # short
                order = await trading_service.futures_open_short(
                    request.exchange, request.symbol, request.amount,
                    request.leverage, request.price
                )
        else:  # close
            if request.side == "long":
                order = await trading_service.futures_close_long(
                    request.exchange, request.symbol, request.amount, request.price
                )
            else:  # short
                order = await trading_service.futures_close_short(
                    request.exchange, request.symbol, request.amount, request.price
                )
        
        return {"success": True, "order": order}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/futures/close-all")
async def futures_close_all(
    exchange: str = Query("okx", description="交易所"),
    symbol: str = Query(..., description="交易对")
):
    """
    平掉所有仓位
    """
    try:
        results = await trading_service.futures_close_all(exchange, symbol)
        return {"success": True, "closed": len(results), "orders": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 订单管理
# ============================================

@router.get("/orders/open")
async def get_open_orders(
    exchange: str = Query("okx", description="交易所"),
    symbol: Optional[str] = Query(None, description="交易对")
):
    """
    获取未成交订单
    """
    try:
        orders = await trading_service.get_open_orders(exchange, symbol)
        return {"exchange": exchange, "orders": orders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders/history")
async def get_order_history(
    exchange: str = Query("okx", description="交易所"),
    symbol: Optional[str] = Query(None, description="交易对"),
    limit: int = Query(50, ge=1, le=200)
):
    """
    获取历史订单
    """
    try:
        orders = await trading_service.get_order_history(exchange, symbol, limit)
        return {"exchange": exchange, "orders": orders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/order/{order_id}")
async def get_order(
    order_id: str,
    exchange: str = Query(..., description="交易所"),
    symbol: str = Query(..., description="交易对")
):
    """
    获取订单详情
    """
    try:
        order = await trading_service.get_order(exchange, order_id, symbol)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        return order
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/order/{order_id}")
async def cancel_order(
    order_id: str,
    exchange: str = Query(..., description="交易所"),
    symbol: str = Query(..., description="交易对")
):
    """
    撤销订单
    """
    try:
        result = await trading_service.cancel_order(exchange, order_id, symbol)
        return {"success": True, "message": "Order cancelled", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/orders/all")
async def cancel_all_orders(
    exchange: str = Query("okx", description="交易所"),
    symbol: Optional[str] = Query(None, description="交易对")
):
    """
    撤销所有订单
    """
    try:
        count = await trading_service.cancel_all_orders(exchange, symbol)
        return {"success": True, "cancelled": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades")
async def get_my_trades(
    exchange: str = Query("okx", description="交易所"),
    symbol: str = Query(..., description="交易对"),
    limit: int = Query(50, ge=1, le=200)
):
    """
    获取成交记录
    """
    try:
        trades = await trading_service.get_my_trades(exchange, symbol, limit)
        return {"exchange": exchange, "symbol": symbol, "trades": trades}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 风险检查
# ============================================

@router.post("/check-risk")
async def check_order_risk(
    exchange: str = Query("okx"),
    symbol: str = Query(...),
    side: str = Query(...),
    amount: float = Query(...),
    price: Optional[float] = Query(None)
):
    """
    下单前风险检查
    """
    try:
        result = await trading_service.check_order_risk(
            exchange, symbol, side, amount, price
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
