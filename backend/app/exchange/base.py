"""
交易所基类
封装 CCXT 的通用操作
"""
import os
from typing import List, Dict, Optional, Any
from abc import ABC, abstractmethod
import ccxt
import logging

logger = logging.getLogger(__name__)


def _get_proxy() -> Optional[str]:
    """获取代理配置（延迟读取，确保 dotenv 已加载）"""
    return os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY') or None


def _is_proxy_alive(proxy: str) -> bool:
    """检测代理端口是否可连通"""
    import socket
    try:
        # 从 http://host:port 中提取 host 和 port
        from urllib.parse import urlparse
        parsed = urlparse(proxy)
        host = parsed.hostname or '127.0.0.1'
        port = parsed.port or 7890
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


class BaseExchange(ABC):
    """交易所基类"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.exchange: ccxt.Exchange = None
        self._markets_loaded = False
    
    @property
    @abstractmethod
    def name(self) -> str:
        """交易所名称"""
        pass
    
    @abstractmethod
    def _create_exchange(self) -> ccxt.Exchange:
        """创建交易所实例"""
        pass
    
    def _apply_proxy(self):
        """
        智能代理配置：
        1. 检查 .env 中的代理配置
        2. 探测代理端口是否可用
        3. 代理可用则启用，不可用则直连
        """
        proxy = _get_proxy()
        if proxy:
            if _is_proxy_alive(proxy):
                self.exchange.proxies = {
                    'http': proxy,
                    'https': proxy,
                }
                logger.info(f"Exchange {self.name} using proxy: {proxy}")
            else:
                # 代理配置了但端口不通，清除代理尝试直连
                self.exchange.proxies = {}
                logger.warning(
                    f"Exchange {self.name}: proxy {proxy} is not reachable, "
                    f"will try direct connection"
                )
        else:
            logger.info(f"Exchange {self.name}: no proxy configured, using direct connection")
    
    def initialize(self):
        """初始化交易所"""
        self.exchange = self._create_exchange()
        
        if self.exchange is None:
            raise RuntimeError(f"Exchange {self.name}: _create_exchange() returned None")
        
        self._apply_proxy()
        logger.info(f"Exchange {self.name} initialized")
    
    def load_markets(self, force: bool = False):
        """
        加载市场信息。
        支持重试，如果第一轮（带代理或直连）失败，
        会自动切换策略（有代理→去代理直连，无代理→加代理）再试一轮。
        """
        if self._markets_loaded and not force:
            return
        if not self.exchange:
            raise RuntimeError(f"Exchange {self.name} not initialized")
        
        import time as _time
        
        # 第一轮：当前配置尝试 2 次
        for attempt in range(2):
            try:
                self.exchange.load_markets()
                self._markets_loaded = True
                return
            except Exception as e:
                logger.warning(
                    f"Exchange {self.name} load_markets attempt {attempt + 1}/2 failed: {e}"
                )
                if attempt < 1:
                    _time.sleep(2)
        
        # 第二轮：切换代理策略后再试
        proxy = _get_proxy()
        current_proxy = self.exchange.proxies.get('https') if self.exchange.proxies else None
        
        if current_proxy:
            # 之前走代理失败了，尝试直连
            logger.info(f"Exchange {self.name}: proxy failed, trying direct connection...")
            self.exchange.proxies = {}
        elif proxy:
            # 之前直连失败了，尝试走代理（可能代理刚启动）
            logger.info(f"Exchange {self.name}: direct failed, trying proxy {proxy}...")
            self.exchange.proxies = {'http': proxy, 'https': proxy}
        else:
            # 没有代理可切换，直接报错
            raise RuntimeError(
                f"Exchange {self.name}: load_markets failed after retries. "
                f"请检查网络连接或配置代理。"
            )
        
        # 切换后再试 2 次
        last_error = None
        for attempt in range(2):
            try:
                self.exchange.load_markets()
                self._markets_loaded = True
                logger.info(f"Exchange {self.name}: load_markets succeeded after switching connection mode")
                return
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Exchange {self.name} load_markets (switched mode) attempt {attempt + 1}/2 failed: {e}"
                )
                if attempt < 1:
                    _time.sleep(2)
        
        raise RuntimeError(
            f"Exchange {self.name}: load_markets failed with both proxy and direct connection. "
            f"Last error: {last_error}. "
            f"请检查: 1) 代理软件是否运行 2) 网络是否能访问 okx.com"
        )
    
    # ============================================
    # 公共接口 (无需 API Key)
    # ============================================
    
    def fetch_ticker(self, symbol: str) -> Dict:
        """获取单个交易对行情"""
        self.load_markets()
        ticker = self.exchange.fetch_ticker(symbol)
        return self._format_ticker(ticker)
    
    def fetch_tickers(self, symbols: List[str] = None) -> List[Dict]:
        """获取多个交易对行情
        
        优化：先拉取全量 tickers（一次 API 调用），再过滤需要的 symbols。
        注意：某些交易所（如 OKX）无参数调用时返回的 key 是合约格式
        (如 BTC/USDT:USDT)，需要做映射匹配现货 symbol (BTC/USDT)。
        """
        self.load_markets()
        # 不传 symbols，让交易所一次性返回所有 tickers（单次 API 调用）
        all_tickers = self.exchange.fetch_tickers()
        
        if symbols:
            # 构建反向映射：将合约 key (BTC/USDT:USDT) 映射为现货 key (BTC/USDT)
            # 方便用现货 symbol 查找
            spot_map: Dict[str, Any] = {}
            for key, ticker in all_tickers.items():
                # 提取现货部分：BTC/USDT:USDT -> BTC/USDT
                spot_key = key.split(':')[0] if ':' in key else key
                # 优先保留精确匹配（现货本身），其次用合约映射
                if spot_key not in spot_map or ':' not in key:
                    spot_map[spot_key] = ticker
            
            result = []
            for s in symbols:
                ticker = all_tickers.get(s) or spot_map.get(s)
                if ticker:
                    formatted = self._format_ticker(ticker)
                    # 确保返回的 symbol 是请求的格式（现货格式）
                    formatted['symbol'] = s
                    result.append(formatted)
            return result
        
        return [self._format_ticker(t) for t in all_tickers.values()]
    
    def fetch_ohlcv(self, symbol: str, timeframe: str = '1h', 
                    limit: int = 100, since: int = None) -> List[Dict]:
        """获取 K 线数据"""
        self.load_markets()
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since, limit)
        return [self._format_kline(k) for k in ohlcv]
    
    def fetch_order_book(self, symbol: str, limit: int = 20) -> Dict:
        """获取订单簿"""
        self.load_markets()
        orderbook = self.exchange.fetch_order_book(symbol, limit)
        return {
            'exchange': self.name,
            'symbol': symbol,
            'bids': orderbook['bids'],
            'asks': orderbook['asks'],
            'timestamp': orderbook.get('timestamp')
        }
    
    def fetch_trades(self, symbol: str, limit: int = 50) -> List[Dict]:
        """获取最近成交"""
        self.load_markets()
        trades = self.exchange.fetch_trades(symbol, limit=limit)
        return [self._format_trade(t) for t in trades]
    
    def get_symbols(self, quote: str = 'USDT') -> List[str]:
        """获取交易对列表"""
        self.load_markets()
        symbols = []
        for symbol, market in self.exchange.markets.items():
            if market.get('quote') == quote and market.get('active'):
                symbols.append(symbol)
        return sorted(symbols)
    
    # ============================================
    # 资金费率相关
    # ============================================
    
    def fetch_funding_rate(self, symbol: str) -> Optional[Dict]:
        """获取资金费率"""
        try:
            # 不同交易所实现不同，子类可重写
            if hasattr(self.exchange, 'fetch_funding_rate'):
                rate = self.exchange.fetch_funding_rate(symbol)
                return self._format_funding_rate(rate, symbol)
        except Exception as e:
            logger.warning(f"Failed to fetch funding rate for {symbol}: {e}")
        return None
    
    def fetch_funding_rates(self, symbols: List[str] = None) -> List[Dict]:
        """获取多个交易对资金费率"""
        rates = []
        if symbols is None:
            symbols = self.get_perpetual_symbols()
        
        for symbol in symbols:
            rate = self.fetch_funding_rate(symbol)
            if rate:
                rates.append(rate)
        
        return rates
    
    def get_perpetual_symbols(self) -> List[str]:
        """获取永续合约交易对"""
        self.load_markets()
        symbols = []
        for symbol, market in self.exchange.markets.items():
            if market.get('swap') and market.get('active'):
                symbols.append(symbol)
        return symbols
    
    # ============================================
    # 私有接口 (需要 API Key)
    # ============================================
    
    def fetch_balance(self) -> Dict:
        """获取账户余额"""
        balance = self.exchange.fetch_balance()
        return self._format_balance(balance)
    
    def fetch_positions(self, symbols: List[str] = None) -> List[Dict]:
        """获取持仓"""
        positions = self.exchange.fetch_positions(symbols)
        return [self._format_position(p) for p in positions if p.get('contracts', 0) > 0]
    
    def create_order(self, symbol: str, type: str, side: str, 
                     amount: float, price: float = None, params: Dict = None) -> Dict:
        """下单"""
        order = self.exchange.create_order(symbol, type, side, amount, price, params or {})
        return self._format_order(order)
    
    def cancel_order(self, order_id: str, symbol: str) -> Dict:
        """撤单"""
        return self.exchange.cancel_order(order_id, symbol)
    
    def fetch_open_orders(self, symbol: str = None) -> List[Dict]:
        """获取未成交订单"""
        orders = self.exchange.fetch_open_orders(symbol)
        return [self._format_order(o) for o in orders]
    
    def fetch_my_trades(self, symbol: str, limit: int = 50) -> List[Dict]:
        """获取成交记录"""
        trades = self.exchange.fetch_my_trades(symbol, limit=limit)
        return [self._format_trade(t) for t in trades]
    
    # ============================================
    # 数据格式化
    # ============================================
    
    def _format_ticker(self, ticker: Dict) -> Dict:
        """格式化行情数据"""
        return {
            'exchange': self.name,
            'symbol': ticker.get('symbol'),
            'last': ticker.get('last'),
            'bid': ticker.get('bid'),
            'ask': ticker.get('ask'),
            'high': ticker.get('high'),
            'low': ticker.get('low'),
            'volume': ticker.get('baseVolume'),
            'quote_volume': ticker.get('quoteVolume'),
            'change': ticker.get('change'),
            'change_percent': ticker.get('percentage'),
            'timestamp': ticker.get('timestamp')
        }
    
    def _format_kline(self, kline: List) -> Dict:
        """格式化 K 线数据"""
        return {
            'timestamp': kline[0],
            'open': kline[1],
            'high': kline[2],
            'low': kline[3],
            'close': kline[4],
            'volume': kline[5]
        }
    
    def _format_trade(self, trade: Dict) -> Dict:
        """格式化成交数据"""
        return {
            'id': str(trade.get('id')),
            'timestamp': trade.get('timestamp'),
            'symbol': trade.get('symbol'),
            'side': trade.get('side'),
            'price': trade.get('price'),
            'amount': trade.get('amount')
        }
    
    def _format_funding_rate(self, rate: Dict, symbol: str) -> Dict:
        """格式化资金费率"""
        return {
            'exchange': self.name,
            'symbol': symbol,
            'current_rate': rate.get('fundingRate'),
            'predicted_rate': rate.get('nextFundingRate'),
            'next_funding_time': rate.get('fundingTimestamp'),
            'mark_price': rate.get('markPrice'),
            'index_price': rate.get('indexPrice')
        }
    
    def _format_balance(self, balance: Dict) -> List[Dict]:
        """格式化余额"""
        result = []
        for currency, data in balance.items():
            if currency in ['info', 'timestamp', 'datetime', 'free', 'used', 'total']:
                continue
            if isinstance(data, dict) and data.get('total', 0) > 0:
                result.append({
                    'currency': currency,
                    'free': data.get('free', 0),
                    'used': data.get('used', 0),
                    'total': data.get('total', 0)
                })
        return result
    
    def _format_position(self, position: Dict) -> Dict:
        """格式化持仓"""
        return {
            'exchange': self.name,
            'symbol': position.get('symbol'),
            'side': position.get('side'),
            'amount': position.get('contracts'),
            'entry_price': position.get('entryPrice'),
            'mark_price': position.get('markPrice'),
            'liquidation_price': position.get('liquidationPrice'),
            'unrealized_pnl': position.get('unrealizedPnl'),
            'leverage': position.get('leverage'),
            'margin_mode': position.get('marginMode')
        }
    
    def _format_order(self, order: Dict) -> Dict:
        """格式化订单"""
        return {
            'id': order.get('id'),
            'exchange': self.name,
            'symbol': order.get('symbol'),
            'side': order.get('side'),
            'type': order.get('type'),
            'price': order.get('price'),
            'amount': order.get('amount'),
            'filled': order.get('filled', 0),
            'remaining': order.get('remaining'),
            'status': order.get('status'),
            'timestamp': order.get('timestamp')
        }
