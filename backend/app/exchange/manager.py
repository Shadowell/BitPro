"""
交易所管理器
统一管理多个交易所实例 — 仅使用真实 OKX 交易所，不使用 Mock 数据
"""
import os
from typing import Dict, Optional, List
import logging
import time

from .base import BaseExchange
from .okx import OKXExchange

logger = logging.getLogger(__name__)


class ExchangeManager:
    """交易所管理器（仅 OKX，纯真实数据）"""
    
    EXCHANGE_CLASSES = {
        'okx': OKXExchange,
    }
    
    def __init__(self):
        self._exchanges: Dict[str, BaseExchange] = {}
        self._initialized = False
        self._last_retry_time: float = 0
        self._retry_interval: float = 30  # 重试间隔 30 秒
    
    def init_exchanges(self):
        """
        初始化交易所。
        如果连接失败不会回退到 Mock，而是保持空状态，
        后续请求时会根据间隔自动重试连接。
        """
        if self._initialized:
            return
        
        for name, cls in self.EXCHANGE_CLASSES.items():
            try:
                exchange = cls()
                exchange.initialize()
                
                # 尝试加载市场（测试连接），但不强制
                try:
                    exchange.load_markets()
                    logger.info(f"Exchange {name} initialized and markets loaded successfully")
                except Exception as e:
                    # load_markets 失败不要紧，后续请求时会懒加载重试
                    logger.warning(f"Exchange {name} initialized but load_markets failed (will retry lazily): {e}")
                
                self._exchanges[name] = exchange
            except Exception as e:
                logger.error(f"Failed to initialize exchange {name}: {e}")
        
        if not self._exchanges:
            logger.error(
                "OKX 交易所初始化失败！请检查: "
                "1) .env 中 OKX_API_KEY/OKX_API_SECRET/OKX_PASSPHRASE 是否正确 "
                "2) 代理 HTTP_PROXY/HTTPS_PROXY 是否可用 "
                "3) 网络是否能访问 okx.com"
            )
        
        self._initialized = True
    
    def _try_reinit(self):
        """
        当交易所不可用时尝试重新初始化（有间隔限制防止频繁重试）
        """
        now = time.time()
        if now - self._last_retry_time < self._retry_interval:
            return
        
        self._last_retry_time = now
        logger.info("Retrying exchange initialization...")
        
        for name, cls in self.EXCHANGE_CLASSES.items():
            if name in self._exchanges:
                continue  # 已经成功的不重试
            try:
                exchange = cls()
                exchange.initialize()
                exchange.load_markets()
                self._exchanges[name] = exchange
                logger.info(f"Exchange {name} re-initialized successfully")
            except Exception as e:
                logger.warning(f"Retry init exchange {name} failed: {e}")
    
    def get_exchange(self, name: str) -> Optional[BaseExchange]:
        """获取交易所实例"""
        if not self._initialized:
            self.init_exchanges()
        
        exchange = self._exchanges.get(name.lower())
        
        # 如果交易所不可用，尝试重新初始化
        if exchange is None:
            self._try_reinit()
            exchange = self._exchanges.get(name.lower())
        
        return exchange
    
    def get_all_exchanges(self) -> Dict[str, BaseExchange]:
        """获取所有交易所实例"""
        if not self._initialized:
            self.init_exchanges()
        
        return self._exchanges
    
    def list_exchanges(self) -> List[str]:
        """列出所有可用交易所"""
        return list(self.EXCHANGE_CLASSES.keys())
    
    def is_supported(self, name: str) -> bool:
        """检查交易所是否支持"""
        return name.lower() in self.EXCHANGE_CLASSES


# 全局交易所管理器实例
exchange_manager = ExchangeManager()
