"""
自动化交易编排器 (Auto Trader Orchestrator)
================================================
将策略引擎、风控模块、信号系统整合为一个完整的自动化交易系统。

功能：
1. 策略调度 - 自动执行策略循环
2. 实时监控 - 仓位状态、PnL 追踪
3. 风控熔断 - 自动检测并触发保护机制
4. 事件日志 - 完整的交易和系统日志
5. 状态报告 - 实时运行状态仪表盘
"""
import asyncio
import time
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
import traceback

from app.services.auto_strategies import (
    ProStrategyBase, create_strategy, STRATEGY_REGISTRY, STRATEGY_INFO
)
from app.services.risk_manager import RiskManager, RiskConfig, RiskLevel
from app.services.signal_analyzer import analyze_market
from app.exchange import exchange_manager

logger = logging.getLogger(__name__)


class TraderState(str, Enum):
    """交易系统状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    CIRCUIT_BREAKER = "circuit_breaker"


@dataclass
class TradeEvent:
    """交易事件"""
    timestamp: float
    event_type: str   # signal / order / fill / stop_loss / take_profit / error / system
    strategy: str
    symbol: str
    details: Dict[str, Any]
    
    def to_dict(self) -> Dict:
        return {
            'time': datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
            'type': self.event_type,
            'strategy': self.strategy,
            'symbol': self.symbol,
            'details': self.details,
        }


@dataclass
class PerformanceMetrics:
    """性能指标"""
    total_pnl: float = 0
    total_pnl_pct: float = 0
    realized_pnl: float = 0
    unrealized_pnl: float = 0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0
    profit_factor: float = 0
    max_drawdown: float = 0
    current_drawdown: float = 0
    sharpe_ratio: float = 0
    avg_trade_duration: float = 0  # 秒
    best_trade: float = 0
    worst_trade: float = 0
    
    def to_dict(self) -> Dict:
        return {
            'total_pnl': round(self.total_pnl, 2),
            'total_pnl_pct': round(self.total_pnl_pct, 2),
            'realized_pnl': round(self.realized_pnl, 2),
            'unrealized_pnl': round(self.unrealized_pnl, 2),
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': round(self.win_rate, 1),
            'profit_factor': round(self.profit_factor, 2),
            'max_drawdown': round(self.max_drawdown, 2),
            'current_drawdown': round(self.current_drawdown, 2),
            'best_trade': round(self.best_trade, 2),
            'worst_trade': round(self.worst_trade, 2),
        }


class AutoTrader:
    """
    自动化交易编排器
    ==================
    使用方法:
    
    trader = AutoTrader()
    
    # 配置
    trader.configure(
        exchange='okx',
        strategy_type='smart_trend',
        symbol='BTC/USDT:USDT',
        timeframe='1h',
        initial_equity=66.0,
        strategy_config={'ema_fast': 9, 'ema_mid': 21, 'ema_slow': 55},
        risk_config={'risk_per_trade_pct': 0.02, 'max_daily_loss_pct': 0.05}
    )
    
    # 启动
    await trader.start()
    
    # 查看状态
    status = trader.get_status()
    
    # 停止
    await trader.stop()
    """
    
    def __init__(self):
        self.state = TraderState.IDLE
        self._strategy: Optional[ProStrategyBase] = None
        self._exchange_name: str = ""
        self._symbol: str = ""
        self._timeframe: str = "1h"
        self._higher_timeframe: str = ""  # 多时间框架用
        self._initial_equity: float = 0
        self._current_equity: float = 0
        self._equity_peak: float = 0
        
        # 运行时
        self._task: Optional[asyncio.Task] = None
        self._loop_interval: int = 30  # 秒
        self._events: List[TradeEvent] = []
        self._metrics = PerformanceMetrics()
        self._pnl_history: List[Dict] = []  # {timestamp, equity}
        self._started_at: Optional[float] = None
        
        # 干运行模式 (不实际下单，只记录信号)
        self._dry_run: bool = True
    
    # ========================================
    # 配置
    # ========================================
    
    def configure(self, exchange: str, strategy_type: str, symbol: str,
                  timeframe: str = '1h', initial_equity: float = 100,
                  strategy_config: Dict = None, risk_config: Dict = None,
                  higher_timeframe: str = '', loop_interval: int = 30,
                  dry_run: bool = True):
        """
        配置自动交易系统
        
        Args:
            exchange: 交易所名称 (okx)
            strategy_type: 策略类型 (见 STRATEGY_REGISTRY)
            symbol: 交易对 (如 BTC/USDT:USDT)
            timeframe: K线周期 (1m/5m/15m/1h/4h/1d)
            initial_equity: 初始资金 (USDT)
            strategy_config: 策略参数
            risk_config: 风控参数
            higher_timeframe: 大周期 (多时间框架策略用)
            loop_interval: 循环间隔(秒)
            dry_run: 干运行模式 (True=不实际下单)
        """
        self._exchange_name = exchange
        self._symbol = symbol
        self._timeframe = timeframe
        self._higher_timeframe = higher_timeframe
        self._initial_equity = initial_equity
        self._current_equity = initial_equity
        self._equity_peak = initial_equity
        self._loop_interval = loop_interval
        self._dry_run = dry_run
        
        # 创建策略
        config = strategy_config or {}
        config['symbol'] = symbol
        if risk_config:
            config['risk'] = risk_config
        
        self._strategy = create_strategy(strategy_type, config)
        self._strategy.initialize(initial_equity)
        
        self._add_event("system", "", {
            'message': f'系统配置完成',
            'exchange': exchange,
            'strategy': strategy_type,
            'symbol': symbol,
            'timeframe': timeframe,
            'initial_equity': initial_equity,
            'dry_run': dry_run,
        })
        
        self.state = TraderState.IDLE
        logger.info(f"AutoTrader configured: {strategy_type} on {exchange} {symbol} {timeframe}")
    
    # ========================================
    # 启停控制
    # ========================================
    
    async def start(self):
        """启动自动交易"""
        if self.state == TraderState.RUNNING:
            logger.warning("AutoTrader is already running")
            return
        
        if not self._strategy:
            raise ValueError("请先调用 configure() 配置系统")
        
        self.state = TraderState.RUNNING
        self._started_at = time.time()
        
        self._add_event("system", "", {'message': '自动交易系统启动'})
        
        # 启动主循环
        self._task = asyncio.create_task(self._main_loop())
        logger.info("AutoTrader started")
    
    async def stop(self):
        """停止自动交易"""
        self.state = TraderState.STOPPED
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        self._add_event("system", "", {'message': '自动交易系统停止'})
        logger.info("AutoTrader stopped")
    
    async def pause(self):
        """暂停"""
        self.state = TraderState.PAUSED
        self._add_event("system", "", {'message': '系统暂停'})
    
    async def resume(self):
        """恢复"""
        if self.state == TraderState.PAUSED:
            self.state = TraderState.RUNNING
            self._add_event("system", "", {'message': '系统恢复'})
    
    # ========================================
    # 主循环
    # ========================================
    
    async def _main_loop(self):
        """策略主循环"""
        logger.info("Main trading loop started")
        
        while self.state == TraderState.RUNNING:
            try:
                await self._execute_cycle()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Trading cycle error: {e}")
                logger.error(traceback.format_exc())
                self._add_event("error", self._symbol, {
                    'message': f'循环异常: {str(e)}'
                })
                # 连续错误保护
                await asyncio.sleep(min(self._loop_interval * 2, 120))
                continue
            
            # 等待下一轮
            await asyncio.sleep(self._loop_interval)
        
        logger.info("Main trading loop ended")
    
    async def _execute_cycle(self):
        """执行一轮策略循环"""
        if self.state == TraderState.PAUSED:
            return
        
        exchange = exchange_manager.get_exchange(self._exchange_name)
        if not exchange:
            logger.error(f"Exchange {self._exchange_name} not available")
            return
        
        # 1. 获取市场数据
        try:
            klines = exchange.fetch_ohlcv(
                self._symbol, self._timeframe, limit=200
            )
        except Exception as e:
            logger.warning(f"Failed to fetch klines: {e}")
            return
        
        if not klines or len(klines) < 30:
            return
        
        # 大周期数据 (可选)
        klines_higher = None
        if self._higher_timeframe:
            try:
                klines_higher = exchange.fetch_ohlcv(
                    self._symbol, self._higher_timeframe, limit=200
                )
            except:
                pass
        
        # 获取资金费率 (仅合约交易对, 如 BTC/USDT:USDT)
        funding_rate = None
        predicted_rate = None
        if ':' in self._symbol:  # 仅合约品种获取资金费率
            try:
                funding = exchange.fetch_funding_rate(self._symbol)
                if funding:
                    funding_rate = funding.get('current_rate')
                    predicted_rate = funding.get('predicted_rate')
            except:
                pass
        
        # 2. 更新账户信息 (dry_run模式使用虚拟资金)
        if not self._dry_run:
            try:
                balance = exchange.fetch_balance()
                usdt_balance = 0
                for b in balance:
                    if isinstance(b, dict) and b.get('currency') == 'USDT':
                        usdt_balance = b.get('total', 0)
                        break
                if usdt_balance > 0:
                    self._current_equity = usdt_balance
                    if self._current_equity > self._equity_peak:
                        self._equity_peak = self._current_equity
            except Exception as e:
                logger.debug(f"Balance fetch error: {e}")
        
        # 3. 执行策略
        result = self._strategy.execute(
            klines, self._current_equity,
            klines_higher=klines_higher,
            funding_rate=funding_rate,
            predicted_rate=predicted_rate,
        )
        
        action = result.get('action', 'hold')
        
        # 4. 记录信号
        if action != 'hold':
            self._add_event("signal", self._symbol, {
                'action': action,
                'confidence': result.get('confidence'),
                'reason': result.get('signal', {}).get('reason', ''),
                'price': klines[-1]['close'],
            })
        
        # 5. 执行交易 (非 dry-run 模式)
        if action in ('buy', 'sell') and not result.get('action') == 'blocked':
            if self._dry_run:
                self._add_event("order", self._symbol, {
                    'message': f'[模拟] {action.upper()}',
                    'amount': result.get('amount'),
                    'price': result.get('price'),
                    'stop_loss': result.get('stop_loss'),
                    'take_profit': result.get('take_profit'),
                })
            else:
                await self._execute_order(exchange, result)
        
        elif action == 'close':
            pnl = result.get('pnl', 0)
            self._update_metrics_on_close(pnl)
            self._add_event("close", self._symbol, {
                'reason': result.get('reason', ''),
                'pnl': pnl,
                'price': result.get('price'),
            })
            
            if not self._dry_run:
                await self._execute_close(exchange, result)
        
        # 6. 记录权益曲线
        self._pnl_history.append({
            'timestamp': time.time(),
            'equity': self._current_equity,
        })
        
        # 7. 风控状态检查
        risk_status = self._strategy.risk_manager.get_status()
        if risk_status.get('circuit_breaker'):
            self.state = TraderState.CIRCUIT_BREAKER
            self._add_event("system", "", {
                'message': f'风控熔断: {risk_status.get("circuit_breaker_reason")}',
                'level': 'critical',
            })
    
    async def _execute_order(self, exchange, result: Dict):
        """执行实际交易订单"""
        try:
            symbol = result.get('symbol', self._symbol)
            action = result['action']
            amount = result.get('amount', 0)
            price = result.get('price')
            
            if amount <= 0:
                return
            
            # 市价单
            side = 'buy' if action == 'buy' else 'sell'
            order = exchange.create_order(
                symbol=symbol,
                type='market',
                side=side,
                amount=amount,
            )
            
            self._add_event("order", symbol, {
                'message': f'订单已提交: {side.upper()} {amount}',
                'order_id': order.get('id'),
                'price': order.get('price') or price,
                'status': order.get('status'),
            })
            
            # 设置止损止盈 (如果交易所支持条件单)
            stop_loss = result.get('stop_loss')
            take_profit = result.get('take_profit')
            
            if stop_loss:
                try:
                    sl_side = 'sell' if action == 'buy' else 'buy'
                    exchange.create_order(
                        symbol=symbol,
                        type='stop',
                        side=sl_side,
                        amount=amount,
                        price=stop_loss,
                        params={'triggerPrice': stop_loss, 'reduceOnly': True}
                    )
                    logger.info(f"Stop loss order placed at {stop_loss}")
                except Exception as e:
                    logger.warning(f"Failed to place stop loss: {e}")
            
            self._metrics.total_trades += 1
            
        except Exception as e:
            logger.error(f"Order execution failed: {e}")
            self._add_event("error", self._symbol, {
                'message': f'下单失败: {str(e)}'
            })
    
    async def _execute_close(self, exchange, result: Dict):
        """执行平仓"""
        try:
            symbol = result.get('symbol', self._symbol)
            price = result.get('price')
            
            # 获取当前持仓
            positions = exchange.fetch_positions([symbol])
            for pos in positions:
                amount = abs(pos.get('amount', 0) or pos.get('contracts', 0))
                if amount <= 0:
                    continue
                
                side = 'sell' if pos.get('side') == 'long' else 'buy'
                order = exchange.create_order(
                    symbol=symbol,
                    type='market',
                    side=side,
                    amount=amount,
                    params={'reduceOnly': True}
                )
                
                self._add_event("close", symbol, {
                    'message': f'平仓执行: {side} {amount}',
                    'order_id': order.get('id'),
                })
                
        except Exception as e:
            logger.error(f"Close execution failed: {e}")
    
    # ========================================
    # 指标更新
    # ========================================
    
    def _update_metrics_on_close(self, pnl: float):
        """平仓后更新性能指标"""
        self._metrics.realized_pnl += pnl
        self._metrics.total_pnl = self._metrics.realized_pnl + self._metrics.unrealized_pnl
        
        if self._initial_equity > 0:
            self._metrics.total_pnl_pct = self._metrics.total_pnl / self._initial_equity * 100
        
        if pnl > 0:
            self._metrics.winning_trades += 1
            self._metrics.best_trade = max(self._metrics.best_trade, pnl)
        elif pnl < 0:
            self._metrics.losing_trades += 1
            self._metrics.worst_trade = min(self._metrics.worst_trade, pnl)
        
        self._metrics.total_trades = self._metrics.winning_trades + self._metrics.losing_trades
        if self._metrics.total_trades > 0:
            self._metrics.win_rate = self._metrics.winning_trades / self._metrics.total_trades * 100
        
        # 回撤
        if self._equity_peak > 0:
            dd = (self._equity_peak - self._current_equity) / self._equity_peak * 100
            self._metrics.current_drawdown = dd
            self._metrics.max_drawdown = max(self._metrics.max_drawdown, dd)
    
    # ========================================
    # 事件记录
    # ========================================
    
    def _add_event(self, event_type: str, symbol: str, details: Dict):
        """添加事件并持久化到数据库"""
        event = TradeEvent(
            timestamp=time.time(),
            event_type=event_type,
            strategy=self._strategy.name if self._strategy else "",
            symbol=symbol,
            details=details,
        )
        self._events.append(event)
        
        # 限制内存中事件数量
        if len(self._events) > 1000:
            self._events = self._events[-500:]
        
        # 持久化到数据库
        self._persist_event(event)
        
        # 日志
        msg = f"[{event_type.upper()}] {symbol} {details.get('message', json.dumps(details, ensure_ascii=False, default=str))}"
        if event_type == 'error':
            logger.error(msg)
        elif event_type in ('signal', 'order', 'close'):
            logger.info(msg)
        else:
            logger.debug(msg)
    
    def _persist_event(self, event: TradeEvent):
        """持久化事件到 SQLite 数据库"""
        try:
            from app.db.local_db import db_instance as db
            conn = db.get_connection()
            # 确保表存在
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trading_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    strategy TEXT,
                    symbol TEXT,
                    details TEXT,
                    exchange TEXT,
                    dry_run INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                INSERT INTO trading_events (timestamp, event_type, strategy, symbol, details, exchange, dry_run)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                event.timestamp,
                event.event_type,
                event.strategy,
                event.symbol,
                json.dumps(event.details, ensure_ascii=False, default=str),
                self._exchange_name,
                1 if self._dry_run else 0,
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Event persist failed: {e}")

    # ========================================
    # 状态查询
    # ========================================
    
    def get_status(self) -> Dict:
        """获取系统完整状态"""
        risk_status = self._strategy.risk_manager.get_status() if self._strategy else {}
        
        uptime = 0
        if self._started_at:
            uptime = time.time() - self._started_at
        
        return {
            'state': self.state.value,
            'uptime': f"{uptime/3600:.1f}h" if uptime > 3600 else f"{uptime/60:.0f}m",
            'exchange': self._exchange_name,
            'symbol': self._symbol,
            'timeframe': self._timeframe,
            'strategy': self._strategy.name if self._strategy else None,
            'dry_run': self._dry_run,
            'equity': {
                'initial': round(self._initial_equity, 2),
                'current': round(self._current_equity, 2),
                'peak': round(self._equity_peak, 2),
                'change': round(self._current_equity - self._initial_equity, 2),
                'change_pct': round((self._current_equity - self._initial_equity) / max(self._initial_equity, 1) * 100, 2),
            },
            'performance': self._metrics.to_dict(),
            'risk': risk_status,
            'recent_events': [e.to_dict() for e in self._events[-20:]],
        }
    
    def get_events(self, limit: int = 50, event_type: str = None) -> List[Dict]:
        """获取事件列表"""
        events = self._events
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return [e.to_dict() for e in events[-limit:]]
    
    def get_equity_curve(self) -> List[Dict]:
        """获取权益曲线"""
        return self._pnl_history[-500:]
    
    def get_strategy_info(self) -> Dict:
        """获取策略信息"""
        if not self._strategy:
            return {}
        return {
            'name': self._strategy.name,
            'config': self._strategy.config,
            'logs': self._strategy.get_logs(30),
        }
    
    @staticmethod
    def list_strategies() -> Dict:
        """列出所有可用策略"""
        return STRATEGY_INFO
    
    @staticmethod
    def get_strategy_detail(strategy_type: str) -> Dict:
        """获取策略详情"""
        info = STRATEGY_INFO.get(strategy_type, {})
        if not info:
            return {'error': f'Unknown strategy: {strategy_type}'}
        return info


# ============================================
# API 端点接口 (供 FastAPI 路由调用)
# ============================================

# 全局 AutoTrader 实例
auto_trader = AutoTrader()


async def api_configure(config: Dict) -> Dict:
    """API: 配置交易系统"""
    try:
        auto_trader.configure(
            exchange=config.get('exchange', 'okx'),
            strategy_type=config.get('strategy_type', 'smart_trend'),
            symbol=config.get('symbol', 'BTC/USDT:USDT'),
            timeframe=config.get('timeframe', '1h'),
            initial_equity=config.get('initial_equity', 100),
            strategy_config=config.get('strategy_config'),
            risk_config=config.get('risk_config'),
            higher_timeframe=config.get('higher_timeframe', ''),
            loop_interval=config.get('loop_interval', 30),
            dry_run=config.get('dry_run', True),
        )
        return {'status': 'ok', 'message': '系统配置成功'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


async def api_start() -> Dict:
    """API: 启动交易"""
    try:
        await auto_trader.start()
        return {'status': 'ok', 'message': '交易系统已启动'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


async def api_stop() -> Dict:
    """API: 停止交易"""
    try:
        await auto_trader.stop()
        return {'status': 'ok', 'message': '交易系统已停止'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


async def api_status() -> Dict:
    """API: 获取状态"""
    return auto_trader.get_status()


async def api_strategies() -> Dict:
    """API: 列出策略"""
    return AutoTrader.list_strategies()


async def api_analyze(exchange: str, symbol: str, timeframe: str = '1h') -> Dict:
    """API: 技术分析"""
    try:
        ex = exchange_manager.get_exchange(exchange)
        if not ex:
            return {'error': f'Exchange {exchange} not available'}
        
        klines = ex.fetch_ohlcv(symbol, timeframe, limit=200)
        if not klines or len(klines) < 30:
            return {'error': 'Insufficient data'}
        
        analysis = analyze_market(klines, symbol)
        return analysis
    except Exception as e:
        return {'error': str(e)}
