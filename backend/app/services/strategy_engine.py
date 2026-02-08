"""
策略执行引擎
负责策略的加载、执行、监控
"""
import asyncio
import traceback
import json
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import logging
import importlib.util
import sys
from io import StringIO

from app.db.local_db import db_instance as db
from app.exchange import exchange_manager
from app.services.websocket_service import connection_manager

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """策略安全检查异常"""
    pass


class StrategyStatus(str, Enum):
    """策略状态"""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class StrategyContext:
    """策略运行上下文"""
    strategy_id: int
    name: str
    exchange: str
    symbols: List[str]
    config: Dict[str, Any]
    
    # 运行时状态
    status: StrategyStatus = StrategyStatus.STOPPED
    positions: Dict[str, float] = field(default_factory=dict)
    orders: List[Dict] = field(default_factory=list)
    trades: List[Dict] = field(default_factory=list)
    pnl: float = 0.0
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    
    # 统计
    total_trades: int = 0
    win_trades: int = 0
    loss_trades: int = 0


class StrategyEngine:
    """策略执行引擎"""
    
    def __init__(self):
        self._contexts: Dict[int, StrategyContext] = {}
        self._tasks: Dict[int, asyncio.Task] = {}
        self._running = False
        self._lock = asyncio.Lock()
    
    async def start(self):
        """启动引擎，并自动恢复上次 running 状态的策略"""
        if self._running:
            return
        self._running = True
        logger.info("Strategy engine started")

        # 自动恢复 DB 中 running 状态的策略
        await self._restore_running_strategies()

    async def _restore_running_strategies(self):
        """服务重启后，自动恢复之前处于 running 状态的策略"""
        try:
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name FROM strategies WHERE status = 'running'"
            )
            rows = cursor.fetchall()
            conn.close()

            if not rows:
                logger.info("没有需要恢复的策略")
                return

            logger.info(f"发现 {len(rows)} 个需要恢复的策略")
            for row in rows:
                strategy_id = row['id']
                name = row['name']
                try:
                    success = await self.start_strategy(strategy_id)
                    if success:
                        logger.info(f"策略恢复成功: #{strategy_id} {name}")
                    else:
                        logger.warning(f"策略恢复失败: #{strategy_id} {name}")
                        db.update_strategy_status(strategy_id, 'stopped')
                except Exception as e:
                    logger.error(f"策略恢复异常: #{strategy_id} {name}: {e}")
                    db.update_strategy_status(strategy_id, 'stopped')
        except Exception as e:
            logger.error(f"恢复运行中策略失败: {e}")
    
    async def stop(self):
        """停止引擎"""
        self._running = False
        
        # 停止所有策略
        for strategy_id in list(self._tasks.keys()):
            await self.stop_strategy(strategy_id)
        
        logger.info("Strategy engine stopped")
    
    async def load_strategy(self, strategy_id: int) -> Optional[StrategyContext]:
        """加载策略"""
        strategy = db.get_strategy_by_id(strategy_id)
        if not strategy:
            return None
        
        context = StrategyContext(
            strategy_id=strategy_id,
            name=strategy['name'],
            exchange=strategy.get('exchange', 'okx'),
            symbols=strategy.get('symbols', ['BTC/USDT']),
            config=strategy.get('config', {}),
        )
        
        async with self._lock:
            self._contexts[strategy_id] = context
        
        return context
    
    async def start_strategy(self, strategy_id: int) -> bool:
        """启动策略"""
        # 加载策略
        context = self._contexts.get(strategy_id)
        if not context:
            context = await self.load_strategy(strategy_id)
        
        if not context:
            logger.error(f"Strategy {strategy_id} not found")
            return False
        
        if context.status == StrategyStatus.RUNNING:
            logger.warning(f"Strategy {strategy_id} is already running")
            return True
        
        # 获取策略脚本
        strategy = db.get_strategy_by_id(strategy_id)
        if not strategy:
            return False
        
        script_content = strategy.get('script_content', '')
        
        try:
            # 创建执行任务
            task = asyncio.create_task(
                self._run_strategy(context, script_content)
            )
            
            async with self._lock:
                self._tasks[strategy_id] = task
                context.status = StrategyStatus.RUNNING
                context.started_at = datetime.now()
            
            # 更新数据库状态
            db.update_strategy_status(strategy_id, 'running')
            
            logger.info(f"Strategy {strategy_id} ({context.name}) started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start strategy {strategy_id}: {e}")
            context.status = StrategyStatus.ERROR
            context.error_message = str(e)
            db.update_strategy_status(strategy_id, 'error')
            return False
    
    async def stop_strategy(self, strategy_id: int) -> bool:
        """停止策略"""
        async with self._lock:
            if strategy_id in self._tasks:
                task = self._tasks.pop(strategy_id)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            if strategy_id in self._contexts:
                self._contexts[strategy_id].status = StrategyStatus.STOPPED
        
        db.update_strategy_status(strategy_id, 'stopped')
        logger.info(f"Strategy {strategy_id} stopped")
        return True
    
    async def _run_strategy(self, context: StrategyContext, script_content: str):
        """运行策略主循环 — 使用安全沙箱执行用户代码"""
        logger.info(f"Running strategy: {context.name}")
        
        # 创建策略运行环境（白名单模式，只暴露安全的函数）
        strategy_globals = self._create_strategy_env(context)
        
        try:
            # ====== 安全沙箱执行 ======
            # 1. 检查危险代码模式（黑名单过滤）
            self._validate_script_safety(script_content)
            
            # 2. 使用受限的 globals/builtins 执行
            safe_globals = self._create_safe_globals(strategy_globals)
            exec(compile(script_content, f"<strategy:{context.name}>", 'exec'), safe_globals)
            
            # 获取策略函数
            on_init = safe_globals.get('on_init')
            on_tick = safe_globals.get('on_tick')
            on_kline = safe_globals.get('on_kline')
            on_funding = safe_globals.get('on_funding')
            
            # 调用初始化
            if on_init:
                on_init()
            
            # 主循环
            exchange = exchange_manager.get_exchange(context.exchange)
            if not exchange:
                raise ValueError(f"Exchange {context.exchange} not available")
            
            while context.status == StrategyStatus.RUNNING:
                try:
                    for symbol in context.symbols:
                        # 获取行情
                        if on_tick:
                            ticker = exchange.fetch_ticker(symbol)
                            on_tick(ticker)
                        
                        # 获取资金费率 (如果是合约)
                        if on_funding:
                            rate = exchange.fetch_funding_rate(symbol)
                            if rate:
                                on_funding(rate)
                    
                    # 等待下一轮
                    await asyncio.sleep(context.config.get('interval', 10))
                    
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Strategy {context.name} tick error: {e}")
                    await asyncio.sleep(5)
            
        except asyncio.CancelledError:
            logger.info(f"Strategy {context.name} cancelled")
        except SecurityError as e:
            logger.error(f"Strategy {context.name} SECURITY VIOLATION: {e}")
            context.status = StrategyStatus.ERROR
            context.error_message = f"安全检查未通过: {e}"
            db.update_strategy_status(context.strategy_id, 'error')
        except Exception as e:
            logger.error(f"Strategy {context.name} error: {e}")
            logger.error(traceback.format_exc())
            context.status = StrategyStatus.ERROR
            context.error_message = str(e)
            db.update_strategy_status(context.strategy_id, 'error')
    
    def _validate_script_safety(self, script_content: str):
        """
        策略代码安全检查 — 黑名单模式
        禁止导入危险模块、访问文件系统、执行系统命令等
        """
        # 禁止的关键字/模式
        FORBIDDEN_PATTERNS = [
            'import os',
            'import sys',
            'import subprocess',
            'import shutil',
            'import socket',
            'import requests',
            'import http',
            'import urllib',
            'from os',
            'from sys',
            'from subprocess',
            'from shutil',
            '__import__',
            'eval(',
            'exec(',
            'compile(',
            'globals()',
            'locals()',
            '__builtins__',
            '__class__',
            '__subclasses__',
            'open(',
            'file(',
            'getattr(',
            'setattr(',
            'delattr(',
            'breakpoint(',
            'exit(',
            'quit(',
        ]
        
        script_lower = script_content.lower()
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.lower() in script_lower:
                raise SecurityError(
                    f"策略代码包含禁止的操作: '{pattern}'\n"
                    f"策略只能使用提供的 API（buy/sell/get_ticker/log 等），"
                    f"不允许导入外部模块或访问系统资源。"
                )
    
    def _create_safe_globals(self, strategy_env: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建安全的执行环境
        只暴露白名单中的内置函数，阻止访问危险的 builtins
        """
        # 安全的内置函数白名单
        safe_builtins = {
            'True': True,
            'False': False,
            'None': None,
            'print': strategy_env.get('print', print),
            'len': len,
            'range': range,
            'sum': sum,
            'min': min,
            'max': max,
            'abs': abs,
            'round': round,
            'int': int,
            'float': float,
            'str': str,
            'bool': bool,
            'list': list,
            'dict': dict,
            'tuple': tuple,
            'set': set,
            'enumerate': enumerate,
            'zip': zip,
            'map': map,
            'filter': filter,
            'sorted': sorted,
            'reversed': reversed,
            'isinstance': isinstance,
            'type': type,
        }
        
        # 构建安全的 globals
        safe_globals = {
            '__builtins__': safe_builtins,
        }
        
        # 注入策略 API（不含危险的内置函数）
        for key, value in strategy_env.items():
            if key not in ('__builtins__', '__import__'):
                safe_globals[key] = value
        
        return safe_globals
    
    def _create_strategy_env(self, context: StrategyContext) -> Dict[str, Any]:
        """创建策略执行环境"""
        exchange = exchange_manager.get_exchange(context.exchange)
        
        def log(message: str, level: str = 'info'):
            """策略日志"""
            log_func = getattr(logger, level, logger.info)
            log_func(f"[{context.name}] {message}")
            
            # 广播到 WebSocket
            asyncio.create_task(
                connection_manager.broadcast(
                    'strategy', context.exchange, str(context.strategy_id),
                    {'type': 'log', 'message': message, 'level': level}
                )
            )
        
        def buy(symbol: str, amount: float, price: float = None, 
                order_type: str = 'market') -> Optional[str]:
            """买入"""
            log(f"BUY {symbol} amount={amount} price={price} type={order_type}")
            
            if not exchange:
                return None
            
            try:
                order = exchange.create_order(symbol, order_type, 'buy', amount, price)
                
                # 记录交易
                trade_record = {
                    'exchange': context.exchange,
                    'symbol': symbol,
                    'order_id': order.get('id'),
                    'timestamp': int(datetime.now().timestamp() * 1000),
                    'side': 'buy',
                    'type': order_type,
                    'price': order.get('price') or price or 0,
                    'quantity': amount,
                }
                db.insert_strategy_trade(context.strategy_id, trade_record)
                context.trades.append(trade_record)
                context.total_trades += 1
                
                return order.get('id')
            except Exception as e:
                log(f"Buy failed: {e}", 'error')
                return None
        
        def sell(symbol: str, amount: float, price: float = None,
                 order_type: str = 'market') -> Optional[str]:
            """卖出"""
            log(f"SELL {symbol} amount={amount} price={price} type={order_type}")
            
            if not exchange:
                return None
            
            try:
                order = exchange.create_order(symbol, order_type, 'sell', amount, price)
                
                trade_record = {
                    'exchange': context.exchange,
                    'symbol': symbol,
                    'order_id': order.get('id'),
                    'timestamp': int(datetime.now().timestamp() * 1000),
                    'side': 'sell',
                    'type': order_type,
                    'price': order.get('price') or price or 0,
                    'quantity': amount,
                }
                db.insert_strategy_trade(context.strategy_id, trade_record)
                context.trades.append(trade_record)
                context.total_trades += 1
                
                return order.get('id')
            except Exception as e:
                log(f"Sell failed: {e}", 'error')
                return None
        
        def get_position(symbol: str) -> float:
            """获取持仓"""
            return context.positions.get(symbol, 0)
        
        def set_position(symbol: str, amount: float):
            """设置持仓 (模拟)"""
            context.positions[symbol] = amount
        
        def get_balance() -> List[Dict]:
            """获取余额"""
            if exchange:
                try:
                    return exchange.fetch_balance()
                except:
                    pass
            return []
        
        def get_ticker(symbol: str) -> Optional[Dict]:
            """获取行情"""
            if exchange:
                try:
                    return exchange.fetch_ticker(symbol)
                except:
                    pass
            return None
        
        def get_klines(symbol: str, timeframe: str = '1h', limit: int = 100) -> List[Dict]:
            """获取K线"""
            if exchange:
                try:
                    return exchange.fetch_ohlcv(symbol, timeframe, limit)
                except:
                    pass
            return []
        
        def get_funding_rate(symbol: str) -> Optional[Dict]:
            """获取资金费率"""
            if exchange:
                try:
                    return exchange.fetch_funding_rate(symbol)
                except:
                    pass
            return None
        
        # 返回策略可用的函数和变量
        return {
            # 内置
            'print': lambda *args: log(' '.join(str(a) for a in args)),
            'len': len,
            'range': range,
            'sum': sum,
            'min': min,
            'max': max,
            'abs': abs,
            'round': round,
            
            # 策略函数
            'log': log,
            'buy': buy,
            'sell': sell,
            'get_position': get_position,
            'set_position': set_position,
            'get_balance': get_balance,
            'get_ticker': get_ticker,
            'get_klines': get_klines,
            'get_funding_rate': get_funding_rate,
            
            # 上下文
            'config': context.config,
            'exchange_name': context.exchange,
            'symbols': context.symbols,
        }
    
    def get_strategy_status(self, strategy_id: int) -> Optional[Dict]:
        """获取策略运行状态"""
        context = self._contexts.get(strategy_id)
        if not context:
            return None
        
        return {
            'strategy_id': strategy_id,
            'name': context.name,
            'status': context.status.value,
            'exchange': context.exchange,
            'symbols': context.symbols,
            'pnl': context.pnl,
            'total_trades': context.total_trades,
            'win_trades': context.win_trades,
            'loss_trades': context.loss_trades,
            'positions': context.positions,
            'error_message': context.error_message,
            'started_at': context.started_at.isoformat() if context.started_at else None,
        }
    
    def get_all_running(self) -> List[Dict]:
        """获取所有运行中的策略"""
        running = []
        for strategy_id, context in self._contexts.items():
            if context.status == StrategyStatus.RUNNING:
                running.append(self.get_strategy_status(strategy_id))
        return running


# 全局引擎实例
strategy_engine = StrategyEngine()
