"""
策略基类
所有策略都应继承此类
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """策略基类"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化策略
        
        Args:
            config: 策略配置参数
        """
        self.config = config or {}
        self.name = self.__class__.__name__
        self.is_running = False
        self.positions: Dict[str, float] = {}  # symbol -> amount
        self.orders: List[Dict] = []
        self.trades: List[Dict] = []
        self.pnl = 0.0
        
    @abstractmethod
    def on_init(self):
        """
        策略初始化
        在策略启动时调用一次
        """
        pass
    
    @abstractmethod
    def on_tick(self, ticker: Dict):
        """
        行情 Tick 更新回调
        
        Args:
            ticker: 行情数据 {symbol, last, bid, ask, volume, ...}
        """
        pass
    
    def on_kline(self, kline: Dict):
        """
        K线更新回调
        
        Args:
            kline: K线数据 {timestamp, open, high, low, close, volume}
        """
        pass
    
    def on_funding_rate(self, rate: Dict):
        """
        资金费率更新回调
        
        Args:
            rate: 费率数据 {symbol, current_rate, next_funding_time, ...}
        """
        pass
    
    def on_order_filled(self, order: Dict):
        """
        订单成交回调
        
        Args:
            order: 订单数据
        """
        pass
    
    def on_stop(self):
        """
        策略停止回调
        """
        pass
    
    # ============================================
    # 交易接口 (子类调用)
    # ============================================
    
    def buy(self, symbol: str, amount: float, price: float = None, 
            order_type: str = 'market') -> Optional[str]:
        """
        买入
        
        Args:
            symbol: 交易对
            amount: 数量
            price: 价格 (限价单需要)
            order_type: 订单类型 market/limit
            
        Returns:
            订单ID
        """
        logger.info(f"[{self.name}] BUY {symbol} amount={amount} price={price}")
        # TODO: 实际下单逻辑
        return None
    
    def sell(self, symbol: str, amount: float, price: float = None,
             order_type: str = 'market') -> Optional[str]:
        """
        卖出
        """
        logger.info(f"[{self.name}] SELL {symbol} amount={amount} price={price}")
        # TODO: 实际下单逻辑
        return None
    
    def open_long(self, symbol: str, amount: float, leverage: int = 1,
                  price: float = None) -> Optional[str]:
        """
        开多 (合约)
        """
        logger.info(f"[{self.name}] OPEN LONG {symbol} amount={amount} leverage={leverage}")
        # TODO: 实际下单逻辑
        return None
    
    def open_short(self, symbol: str, amount: float, leverage: int = 1,
                   price: float = None) -> Optional[str]:
        """
        开空 (合约)
        """
        logger.info(f"[{self.name}] OPEN SHORT {symbol} amount={amount} leverage={leverage}")
        # TODO: 实际下单逻辑
        return None
    
    def close_position(self, symbol: str) -> bool:
        """
        平仓
        """
        logger.info(f"[{self.name}] CLOSE POSITION {symbol}")
        # TODO: 实际平仓逻辑
        return True
    
    def cancel_order(self, order_id: str) -> bool:
        """
        撤单
        """
        logger.info(f"[{self.name}] CANCEL ORDER {order_id}")
        # TODO: 实际撤单逻辑
        return True
    
    # ============================================
    # 辅助方法
    # ============================================
    
    def get_position(self, symbol: str) -> float:
        """获取持仓数量"""
        return self.positions.get(symbol, 0)
    
    def get_all_positions(self) -> Dict[str, float]:
        """获取所有持仓"""
        return self.positions.copy()
    
    def log(self, message: str, level: str = 'info'):
        """记录日志"""
        log_func = getattr(logger, level, logger.info)
        log_func(f"[{self.name}] {message}")


class FundingArbitrageStrategy(BaseStrategy):
    """
    资金费率套利策略示例
    当资金费率 > 阈值时，买入现货 + 做空永续
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.min_rate = self.config.get('min_rate', 0.0001)  # 最小费率阈值
        self.position_size = self.config.get('position_size', 0.01)  # 仓位大小
        self.symbols = self.config.get('symbols', ['BTC/USDT'])
        self.in_position = False
    
    def on_init(self):
        self.log(f"Funding Arbitrage Strategy initialized")
        self.log(f"min_rate={self.min_rate}, position_size={self.position_size}")
    
    def on_tick(self, ticker: Dict):
        # 套利策略主要关注资金费率，tick 用于监控价格
        pass
    
    def on_funding_rate(self, rate: Dict):
        symbol = rate.get('symbol')
        current_rate = rate.get('current_rate', 0)
        
        self.log(f"{symbol} funding rate: {current_rate:.4%}")
        
        # 如果费率 > 阈值且未持仓，开仓套利
        if current_rate > self.min_rate and not self.in_position:
            self.log(f"Opening arbitrage position for {symbol}")
            
            # 买入现货
            self.buy(symbol, self.position_size)
            
            # 做空永续
            self.open_short(symbol, self.position_size)
            
            self.in_position = True
        
        # 如果费率转负，平仓
        elif current_rate < 0 and self.in_position:
            self.log(f"Closing arbitrage position for {symbol}")
            
            # 卖出现货
            self.sell(symbol, self.position_size)
            
            # 平空仓
            self.close_position(symbol)
            
            self.in_position = False
    
    def on_stop(self):
        # 策略停止时平仓
        if self.in_position:
            for symbol in self.symbols:
                self.close_position(symbol)
        self.log("Strategy stopped")


class GridTradingStrategy(BaseStrategy):
    """
    网格交易策略示例
    在价格区间内设置买卖网格
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.symbol = self.config.get('symbol', 'BTC/USDT')
        self.price_low = self.config.get('price_low', 40000)
        self.price_high = self.config.get('price_high', 60000)
        self.grid_num = self.config.get('grid_num', 10)
        self.order_amount = self.config.get('order_amount', 0.001)
        
        self.grid_prices = []
        self.grid_orders = {}  # price -> order_id
    
    def on_init(self):
        # 计算网格价格
        step = (self.price_high - self.price_low) / self.grid_num
        self.grid_prices = [
            self.price_low + i * step 
            for i in range(self.grid_num + 1)
        ]
        
        self.log(f"Grid Trading Strategy initialized")
        self.log(f"Price range: {self.price_low} - {self.price_high}")
        self.log(f"Grid prices: {self.grid_prices}")
    
    def on_tick(self, ticker: Dict):
        if ticker.get('symbol') != self.symbol:
            return
        
        current_price = ticker.get('last', 0)
        
        # 检查是否触发网格
        for grid_price in self.grid_prices:
            if grid_price not in self.grid_orders:
                if current_price <= grid_price:
                    # 价格低于网格价，挂买单
                    order_id = self.buy(self.symbol, self.order_amount, grid_price, 'limit')
                    if order_id:
                        self.grid_orders[grid_price] = order_id
    
    def on_order_filled(self, order: Dict):
        # 成交后在对面挂单
        if order.get('side') == 'buy':
            # 买单成交，挂卖单 (加一个网格)
            new_price = order.get('price') + (self.price_high - self.price_low) / self.grid_num
            self.sell(self.symbol, self.order_amount, new_price, 'limit')
        else:
            # 卖单成交，挂买单 (减一个网格)
            new_price = order.get('price') - (self.price_high - self.price_low) / self.grid_num
            self.buy(self.symbol, self.order_amount, new_price, 'limit')
    
    def on_stop(self):
        # 撤销所有挂单
        for order_id in self.grid_orders.values():
            self.cancel_order(order_id)
        self.log("Strategy stopped, all orders cancelled")
