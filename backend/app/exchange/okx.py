"""
OKX 交易所封装
"""
import ccxt
from typing import Dict, List, Optional, Any
import logging

from .base import BaseExchange
from app.core.config import settings

logger = logging.getLogger(__name__)


class OKXExchange(BaseExchange):
    """OKX 交易所"""
    
    @property
    def name(self) -> str:
        return "okx"
    
    def _create_exchange(self) -> ccxt.Exchange:
        """创建 OKX 交易所实例"""
        config = {
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',  # 永续合约
            }
        }
        
        # 如果配置了 API Key
        if settings.OKX_API_KEY and settings.OKX_API_SECRET:
            config['apiKey'] = settings.OKX_API_KEY
            config['secret'] = settings.OKX_API_SECRET
            if settings.OKX_PASSPHRASE:
                config['password'] = settings.OKX_PASSPHRASE
        
        # 测试网
        if settings.OKX_TESTNET:
            config['sandbox'] = True
        
        return ccxt.okx(config)
    
    def fetch_balance(self) -> List[Dict]:
        """
        获取 OKX 账户余额 — 合并 trading（交易账户）和 funding（资金账户）
        OKX 统一账户体系下资产可能分散在不同子账户中，需要合并查询。
        """
        merged: Dict[str, Dict] = {}  # currency -> {free, used, total}

        for acct_type in ['trading', 'funding']:
            try:
                balance = self.exchange.fetch_balance({'type': acct_type})
                for currency, data in balance.items():
                    if currency in ['info', 'timestamp', 'datetime', 'free', 'used', 'total']:
                        continue
                    if not isinstance(data, dict):
                        continue
                    total = data.get('total', 0) or 0
                    free = data.get('free', 0) or 0
                    used = data.get('used', 0) or 0
                    if total <= 0 and free <= 0:
                        continue
                    if currency in merged:
                        merged[currency]['free'] += free
                        merged[currency]['used'] += used
                        merged[currency]['total'] += total
                    else:
                        merged[currency] = {
                            'currency': currency,
                            'free': free,
                            'used': used,
                            'total': total,
                        }
            except Exception as e:
                logger.warning(f"Failed to fetch OKX {acct_type} balance: {e}")

        return list(merged.values())
    
    def fetch_funding_rate(self, symbol: str) -> Optional[Dict]:
        """获取 OKX 资金费率"""
        try:
            self.load_markets()
            
            # 获取资金费率
            funding = self.exchange.fetch_funding_rate(symbol)
            
            return {
                'exchange': self.name,
                'symbol': symbol,
                'current_rate': funding.get('fundingRate'),
                'predicted_rate': funding.get('nextFundingRate'),
                'next_funding_time': funding.get('fundingTimestamp'),
                'mark_price': funding.get('markPrice'),
                'index_price': funding.get('indexPrice')
            }
        except Exception as e:
            logger.warning(f"Failed to fetch OKX funding rate for {symbol}: {e}")
            return None
    
    def fetch_funding_rates(self, symbols: List[str] = None) -> List[Dict]:
        """批量获取资金费率"""
        try:
            self.load_markets()
            
            # OKX 批量获取
            if hasattr(self.exchange, 'publicGetPublicFundingRate'):
                response = self.exchange.publicGetPublicFundingRate()
                
                rates = []
                data = response.get('data', [])
                
                for item in data:
                    inst_id = item.get('instId', '')
                    
                    # 转换为 CCXT 符号格式
                    try:
                        symbol = self.exchange.safe_symbol(inst_id)
                    except:
                        continue
                    
                    if symbols and symbol not in symbols:
                        continue
                    
                    rates.append({
                        'exchange': self.name,
                        'symbol': symbol,
                        'current_rate': float(item.get('fundingRate', 0)),
                        'predicted_rate': float(item.get('nextFundingRate', 0)) if item.get('nextFundingRate') else None,
                        'next_funding_time': int(item.get('fundingTime', 0)),
                        'mark_price': None,
                        'index_price': None
                    })
                
                return rates
            
            return super().fetch_funding_rates(symbols)
            
        except Exception as e:
            logger.error(f"Failed to fetch OKX funding rates: {e}")
            return []
    
    def fetch_funding_history(self, symbol: str, limit: int = 100) -> List[Dict]:
        """获取资金费率历史"""
        try:
            self.load_markets()
            
            market = self.exchange.market(symbol)
            inst_id = market['id']
            
            # 调用 OKX API
            response = self.exchange.publicGetPublicFundingRateHistory({
                'instId': inst_id,
                'limit': str(limit)
            })
            
            history = []
            for item in response.get('data', []):
                history.append({
                    'timestamp': int(item.get('fundingTime', 0)),
                    'rate': float(item.get('realizedRate', 0)),
                    'mark_price': None
                })
            
            return history
            
        except Exception as e:
            logger.error(f"Failed to fetch OKX funding history: {e}")
            return []
