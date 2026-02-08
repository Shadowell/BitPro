"""
模拟盘交易引擎 (Paper Trading Engine)
======================================
Phase 4 核心组件

与回测引擎的区别:
  - 回测: 用历史数据一次性回放
  - 模拟盘: 用实时数据，逐根K线触发信号，模拟真实交易环境

功能:
  1. 从本地DB读取最新K线数据驱动策略
  2. 模拟交易执行 (含滑点/手续费)
  3. 实时仓位/资金/PnL跟踪
  4. 风控熔断系统 (多层保护)
  5. 信号记录 (每一笔买卖原因都记录)
  6. 定时快照 (每日保存模拟盘状态)

使用方式:
    from app.services.paper_trading import PaperTradingEngine

    engine = PaperTradingEngine(
        strategy_name='adaptive_bollinger',
        symbol='BTC/USDT',
        timeframe='4h',
        initial_capital=10000,
    )
    await engine.start()    # 开始模拟
    status = engine.status  # 查看状态
    await engine.stop()     # 停止模拟
"""
import asyncio
import json
import logging
import numpy as np
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

from app.db.local_db import db_instance as db
from app.services.indicators import klines_to_arrays
from app.services.strategy_backtest import (
    Backtest, BacktestConfig, BacktestResultV2, StrategyContext,
    Position, Side, TradeRecord,
)
from app.services.pro_strategies import (
    adaptive_bollinger_strategy, adaptive_bollinger_setup,
    trend_following_strategy, trend_following_setup,
    combo_strategy, combo_strategy_setup,
)
from app.services.strategy_registry import (
    scalping_strategy, scalping_setup,
    momentum_breakout_strategy, momentum_breakout_setup,
)
from app.services.market_regime import (
    detect_regime, setup_regime_indicators, MarketRegime,
)

logger = logging.getLogger(__name__)


# ============================================
# 风控配置
# ============================================

@dataclass
class RiskConfig:
    """风控参数配置"""
    # 账户级止损: 总亏损超过此比例立即停止所有交易
    account_stop_loss: float = 0.15           # 15%

    # 单日止损: 当日亏损超过此比例暂停交易到次日
    daily_stop_loss: float = 0.05             # 5%

    # 单笔最大亏损
    max_loss_per_trade: float = 0.03          # 3%

    # 最大持仓比例
    max_position_pct: float = 0.95            # 95%

    # 连续亏损熔断
    consecutive_loss_limit: int = 5           # 连续5次亏损暂停

    # 波动率熔断: 当ATR百分比超过此值，暂停交易
    volatility_circuit_breaker: float = 0.08  # ATR/价格 > 8% 熔断

    # 最大同时持仓数
    max_open_positions: int = 1

    # 冷却时间 (分钟): 熔断后等待时间
    cooldown_minutes: int = 60


class CircuitBreakerState(str, Enum):
    """熔断状态"""
    NORMAL = 'normal'
    DAILY_LOSS_TRIGGERED = 'daily_loss'
    ACCOUNT_LOSS_TRIGGERED = 'account_loss'
    CONSECUTIVE_LOSS = 'consecutive_loss'
    VOLATILITY_TRIGGERED = 'volatility'
    COOLDOWN = 'cooldown'


@dataclass
class RiskState:
    """风控运行时状态"""
    circuit_breaker: CircuitBreakerState = CircuitBreakerState.NORMAL
    daily_pnl: float = 0.0
    daily_start_equity: float = 0.0
    total_pnl: float = 0.0
    consecutive_losses: int = 0
    last_trade_time: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None
    breaker_reason: str = ''


# ============================================
# 模拟盘引擎
# ============================================

@dataclass
class PaperTradingSnapshot:
    """模拟盘快照"""
    timestamp: str
    equity: float
    capital: float
    position_value: float
    position_side: str
    position_size: float
    position_entry: float
    total_trades: int
    winning_trades: int
    total_pnl: float
    daily_pnl: float
    circuit_breaker: str
    last_signal: str


@dataclass
class SignalRecord:
    """信号记录"""
    timestamp: str
    bar_time: int
    action: str         # buy/sell/hold/blocked
    reason: str         # signal reason or block reason
    price: float
    quantity: float = 0
    regime: str = ''    # market regime
    rsi: float = 0
    atr_pct: float = 0  # ATR/price percentage
    equity: float = 0
    pnl: float = 0


class PaperTradingEngine:
    """
    模拟盘交易引擎

    流程:
    1. 从本地DB加载历史K线
    2. 初始化策略上下文和指标
    3. 逐根K线驱动策略
    4. 策略产生买卖信号 → 风控检查 → 模拟执行
    5. 记录每一笔信号和交易
    """

    def __init__(
        self,
        strategy_name: str = 'adaptive_bollinger',
        exchange: str = 'okx',
        symbol: str = 'BTC/USDT',
        timeframe: str = '4h',
        initial_capital: float = 10000.0,
        commission: float = 0.0004,
        slippage: float = 0.0001,
        stop_loss: float = 0.05,
        risk_config: RiskConfig = None,
    ):
        self.strategy_name = strategy_name
        self.exchange = exchange
        self.symbol = symbol
        self.timeframe = timeframe
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.stop_loss = stop_loss
        self.risk_config = risk_config or RiskConfig()

        # 策略 — 统一从 strategy_registry 获取
        from app.services.strategy_registry import STRATEGY_FUNCTION_MAP, resolve_strategy_by_key
        strategy_info = resolve_strategy_by_key(strategy_name)
        if not strategy_info:
            available = list(STRATEGY_FUNCTION_MAP.keys())
            raise ValueError(f"未知策略: {strategy_name}. 可用: {available}")
        self.strategy_fn = strategy_info['fn']
        self.setup_fn = strategy_info['setup']
        self.strategy_display_name = strategy_info['fn'].__doc__ or strategy_name

        # 状态
        self._running = False
        self._ctx: Optional[StrategyContext] = None
        self.risk_state = RiskState()
        self.signals: List[SignalRecord] = []
        self.snapshots: List[PaperTradingSnapshot] = []

        # 回测配置 (复用v2框架)
        self._bt_config = BacktestConfig(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            start_date='',  # 动态设置
            end_date='',
            initial_capital=initial_capital,
            commission=commission,
            slippage=slippage,
            stop_loss=stop_loss,
        )

    @property
    def status(self) -> Dict[str, Any]:
        """获取当前状态"""
        ctx = self._ctx
        pos = ctx.position if ctx else Position()
        equity = ctx.equity if ctx else self.initial_capital
        capital = ctx.capital if ctx else self.initial_capital

        return {
            'running': self._running,
            'strategy': self.strategy_display_name,
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'equity': round(equity, 2),
            'capital': round(capital, 2),
            'initial_capital': self.initial_capital,
            'total_pnl': round(self.risk_state.total_pnl, 2),
            'total_pnl_pct': round(self.risk_state.total_pnl / self.initial_capital * 100, 2) if self.initial_capital > 0 else 0,
            'daily_pnl': round(self.risk_state.daily_pnl, 2),
            'position': {
                'side': pos.side,
                'size': round(pos.size, 6),
                'entry_price': round(pos.entry_price, 2),
                'is_open': pos.is_open,
            },
            'total_trades': len([t for t in (ctx.trades if ctx else []) if t.side in ('sell', 'cover')]),
            'total_signals': len(self.signals),
            'circuit_breaker': self.risk_state.circuit_breaker.value,
            'breaker_reason': self.risk_state.breaker_reason,
            'consecutive_losses': self.risk_state.consecutive_losses,
        }

    def run_simulation(self, days_back: int = 30) -> Dict[str, Any]:
        """
        运行模拟盘 — 使用最近N天的数据

        这不是实时运行，而是用最近的数据"模拟实盘执行过程"。
        模拟盘和回测的关键区别:
        1. 每根K线都有风控检查
        2. 有熔断机制
        3. 信号都记录
        4. 有账户级/日级止损
        """
        # 计算时间范围
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

        logger.info(f"模拟盘启动: {self.strategy_display_name} | {self.symbol} {self.timeframe} | {start_date}~{end_date}")

        # 加载数据
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

        klines = db.get_klines(
            exchange=self.exchange,
            symbol=self.symbol,
            timeframe=self.timeframe,
            limit=999999,
            start=start_ts,
            end=end_ts,
        )

        if not klines or len(klines) < 50:
            return {
                'status': 'error',
                'message': f'本地数据不足: {len(klines) if klines else 0}条 (需要>=50). '
                           f'请先同步数据: POST /api/v1/data_sync/sync_one',
            }

        # 转换数据
        arrays = klines_to_arrays(klines)

        # 初始化上下文
        ctx = StrategyContext(self._bt_config)
        ctx.timestamp = arrays['timestamp']
        ctx.open = arrays['open']
        ctx.high = arrays['high']
        ctx.low = arrays['low']
        ctx.close = arrays['close']
        ctx.volume = arrays['volume']

        # 设置指标
        from app.services.strategy_backtest import Backtest
        bt = Backtest(self._bt_config, self.strategy_fn, self.setup_fn)
        bt._setup_default_indicators(ctx)
        self.setup_fn(ctx)

        self._ctx = ctx
        self._running = True
        self.risk_state = RiskState(daily_start_equity=self.initial_capital)
        self.signals = []
        self.snapshots = []

        total_bars = len(ctx.close)
        equity_history = []
        current_day = ''

        logger.info(f"模拟盘数据: {total_bars}根K线, 从{start_date}到{end_date}")

        # ====== 逐根K线模拟 ======
        for i in range(total_bars):
            ctx.bar_index = i

            # 更新持仓追踪价格
            if ctx.position.is_open:
                price = ctx.current_price
                ctx.position.highest_price = max(ctx.position.highest_price, price)
                ctx.position.lowest_price = min(ctx.position.lowest_price, price)

            # ---- 日期切换: 重置日级PnL ----
            bar_dt = datetime.fromtimestamp(ctx.current_time / 1000)
            bar_day = bar_dt.strftime('%Y-%m-%d')
            if bar_day != current_day:
                current_day = bar_day
                self.risk_state.daily_pnl = 0
                self.risk_state.daily_start_equity = ctx.equity if ctx.equity > 0 else self.initial_capital
                # 日级熔断重置
                if self.risk_state.circuit_breaker == CircuitBreakerState.DAILY_LOSS_TRIGGERED:
                    self.risk_state.circuit_breaker = CircuitBreakerState.NORMAL
                    self.risk_state.breaker_reason = ''

            # ---- 计算当前权益 ----
            if ctx.position.is_open:
                if ctx.position.side == Side.LONG:
                    ctx.equity = ctx.capital + ctx.position.size * ctx.current_price
                else:
                    unrealized = (ctx.position.entry_price - ctx.current_price) * ctx.position.size
                    ctx.equity = ctx.capital + ctx.position.value + unrealized
            else:
                ctx.equity = ctx.capital

            # ---- 风控检查 ----
            trades_before = len(ctx.trades)
            risk_ok = self._check_risk(ctx, i)

            if risk_ok:
                # 内置止损检查
                bt._check_risk_management(ctx)

                # 策略信号
                self.strategy_fn(ctx)

            # ---- 记录信号 ----
            trades_after = len(ctx.trades)
            if trades_after > trades_before:
                # 有新交易
                for t in ctx.trades[trades_before:]:
                    self._record_signal(ctx, i, t.side, t.reason, t.price, t.quantity)
                    # 更新PnL
                    if t.side in ('sell', 'cover'):
                        self.risk_state.total_pnl += t.pnl
                        self.risk_state.daily_pnl += t.pnl
                        if t.pnl > 0:
                            self.risk_state.consecutive_losses = 0
                        elif t.pnl < 0:
                            self.risk_state.consecutive_losses += 1
            elif not risk_ok:
                self._record_signal(ctx, i, 'blocked', self.risk_state.breaker_reason, ctx.current_price, 0)

            # 记录权益
            equity_history.append(ctx.equity)

            # ---- 每日快照 ----
            if i == total_bars - 1 or (i > 0 and datetime.fromtimestamp(ctx.timestamp[i] / 1000).hour == 0):
                self._take_snapshot(ctx)

        # ====== 最终平仓 ======
        if ctx.position.is_open:
            ctx.bar_index = total_bars - 1
            ctx._close_position('paper_trading_end')
            for t in ctx.trades[len(ctx.trades)-1:]:
                self._record_signal(ctx, total_bars-1, t.side, t.reason, t.price, t.quantity)

        # ====== 计算最终结果 ======
        close_trades = [t for t in ctx.trades if t.side in ('sell', 'cover')]
        wins = [t for t in close_trades if t.pnl > 0]
        losses = [t for t in close_trades if t.pnl < 0]

        equity_arr = np.array(equity_history)
        peak = np.maximum.accumulate(equity_arr)
        drawdown = (peak - equity_arr) / peak * 100
        max_dd = float(np.max(drawdown)) if len(drawdown) > 0 else 0

        # 夏普
        if len(equity_arr) > 1:
            returns = np.diff(equity_arr) / equity_arr[:-1]
            returns = returns[~np.isnan(returns)]
            if len(returns) > 0:
                tf_annual = {'1m': 525600, '5m': 105120, '15m': 35040, '30m': 17520,
                             '1h': 8760, '4h': 2190, '1d': 365, '1w': 52}
                af = tf_annual.get(self.timeframe, 365)
                avg_r = np.mean(returns)
                std_r = np.std(returns, ddof=1)
                sharpe = (avg_r * af) / (std_r * np.sqrt(af)) if std_r > 0 else 0
            else:
                sharpe = 0
        else:
            sharpe = 0

        final_equity = float(equity_arr[-1]) if len(equity_arr) > 0 else self.initial_capital
        total_return = (final_equity - self.initial_capital) / self.initial_capital * 100

        self._running = False

        result = {
            'status': 'completed',
            'strategy': self.strategy_display_name,
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'period': f'{start_date} ~ {end_date}',
            'total_bars': total_bars,

            # 绩效
            'initial_capital': self.initial_capital,
            'final_equity': round(final_equity, 2),
            'total_return_pct': round(total_return, 2),
            'max_drawdown_pct': round(max_dd, 2),
            'sharpe_ratio': round(sharpe, 3),

            # 交易统计
            'total_trades': len(close_trades),
            'winning_trades': len(wins),
            'losing_trades': len(losses),
            'win_rate_pct': round(len(wins) / len(close_trades) * 100, 1) if close_trades else 0,
            'total_pnl': round(sum(t.pnl for t in close_trades), 2),
            'avg_win': round(np.mean([t.pnl for t in wins]), 2) if wins else 0,
            'avg_loss': round(np.mean([t.pnl for t in losses]), 2) if losses else 0,
            'total_fees': round(sum(t.fee for t in ctx.trades), 2),

            # 风控统计
            'risk_events': {
                'total_blocked_signals': len([s for s in self.signals if s.action == 'blocked']),
                'circuit_breaker_triggers': len(set(
                    s.timestamp[:10] for s in self.signals if s.action == 'blocked'
                )),
                'max_consecutive_losses': max(
                    (self.risk_state.consecutive_losses, 0)
                ),
            },

            # 信号列表 (最近50条)
            'recent_signals': [
                {
                    'time': s.timestamp,
                    'action': s.action,
                    'reason': s.reason,
                    'price': s.price,
                    'quantity': s.quantity,
                    'regime': s.regime,
                    'equity': s.equity,
                }
                for s in self.signals[-50:]
            ],

            # 快照
            'snapshots': [
                {
                    'time': snap.timestamp,
                    'equity': snap.equity,
                    'position': snap.position_side,
                    'daily_pnl': snap.daily_pnl,
                    'breaker': snap.circuit_breaker,
                }
                for snap in self.snapshots[-30:]
            ],
        }

        logger.info(
            f"模拟盘完成: {self.strategy_display_name} | "
            f"收益: {total_return:+.2f}% | 夏普: {sharpe:.2f} | "
            f"回撤: {max_dd:.1f}% | 交易: {len(close_trades)}笔 | "
            f"风控拦截: {result['risk_events']['total_blocked_signals']}次"
        )

        return result

    # ============================================
    # 风控系统
    # ============================================

    def _check_risk(self, ctx: StrategyContext, bar_index: int) -> bool:
        """
        多层风控检查

        Returns:
            True = 允许交易
            False = 风控拦截
        """
        rc = self.risk_config
        rs = self.risk_state
        equity = ctx.equity

        # ---- 1. 账户级止损 (不可恢复) ----
        total_loss_pct = (equity - self.initial_capital) / self.initial_capital
        if total_loss_pct <= -rc.account_stop_loss:
            if rs.circuit_breaker != CircuitBreakerState.ACCOUNT_LOSS_TRIGGERED:
                rs.circuit_breaker = CircuitBreakerState.ACCOUNT_LOSS_TRIGGERED
                rs.breaker_reason = f'账户止损触发: 亏损{total_loss_pct*100:.1f}% > {rc.account_stop_loss*100:.0f}%'
                logger.warning(f"[风控] {rs.breaker_reason}")
                # 强制平仓
                if ctx.position.is_open:
                    ctx._close_position('risk_account_stop')
            return False

        # ---- 2. 单日止损 (次日恢复) ----
        if rs.daily_start_equity > 0:
            daily_loss_pct = (equity - rs.daily_start_equity) / rs.daily_start_equity
            if daily_loss_pct <= -rc.daily_stop_loss:
                if rs.circuit_breaker != CircuitBreakerState.DAILY_LOSS_TRIGGERED:
                    rs.circuit_breaker = CircuitBreakerState.DAILY_LOSS_TRIGGERED
                    rs.breaker_reason = f'日止损触发: 今日亏损{daily_loss_pct*100:.1f}% > {rc.daily_stop_loss*100:.0f}%'
                    logger.warning(f"[风控] {rs.breaker_reason}")
                return False

        # ---- 3. 连续亏损熔断 ----
        if rs.consecutive_losses >= rc.consecutive_loss_limit:
            if rs.circuit_breaker != CircuitBreakerState.CONSECUTIVE_LOSS:
                rs.circuit_breaker = CircuitBreakerState.CONSECUTIVE_LOSS
                rs.breaker_reason = f'连续亏损熔断: {rs.consecutive_losses}连亏 >= {rc.consecutive_loss_limit}'
                logger.warning(f"[风控] {rs.breaker_reason}")
            # 连续亏损允许在盈利一笔后恢复
            return False

        # ---- 4. 波动率熔断 ----
        atr = ctx.indicators.get('atr_14')
        if atr is not None and bar_index < len(atr) and not np.isnan(atr[bar_index]):
            price = ctx.current_price
            if price > 0:
                atr_pct = atr[bar_index] / price
                if atr_pct > rc.volatility_circuit_breaker:
                    if rs.circuit_breaker != CircuitBreakerState.VOLATILITY_TRIGGERED:
                        rs.circuit_breaker = CircuitBreakerState.VOLATILITY_TRIGGERED
                        rs.breaker_reason = f'波动率熔断: ATR/Price={atr_pct*100:.1f}% > {rc.volatility_circuit_breaker*100:.0f}%'
                        logger.warning(f"[风控] {rs.breaker_reason}")
                    return False

        # ---- 5. 冷却期检查 ----
        if rs.cooldown_until:
            bar_dt = datetime.fromtimestamp(ctx.current_time / 1000)
            if bar_dt < rs.cooldown_until:
                return False
            else:
                rs.cooldown_until = None

        # 全部通过 → 正常状态
        if rs.circuit_breaker not in (
            CircuitBreakerState.NORMAL,
            CircuitBreakerState.ACCOUNT_LOSS_TRIGGERED,
        ):
            rs.circuit_breaker = CircuitBreakerState.NORMAL
            rs.breaker_reason = ''

        return True

    # ============================================
    # 记录
    # ============================================

    def _record_signal(self, ctx: StrategyContext, bar_index: int,
                       action: str, reason: str, price: float, quantity: float):
        """记录一条信号"""
        i = bar_index
        rsi = ctx.indicators.get('rsi_14')
        rsi_val = float(rsi[i]) if rsi is not None and not np.isnan(rsi[i]) else 0
        atr = ctx.indicators.get('atr_14')
        atr_pct = float(atr[i] / price * 100) if atr is not None and not np.isnan(atr[i]) and price > 0 else 0

        # 市场状态
        regime = detect_regime(
            ctx.high, ctx.low, ctx.close, i,
            adx_arr=ctx.indicators.get('regime_adx'),
            plus_di_arr=ctx.indicators.get('regime_plus_di'),
            minus_di_arr=ctx.indicators.get('regime_minus_di'),
            vol_percentile_arr=ctx.indicators.get('regime_vol_percentile'),
            sma_slope_arr=ctx.indicators.get('regime_sma_slope'),
        )

        signal = SignalRecord(
            timestamp=datetime.fromtimestamp(ctx.current_time / 1000).strftime('%Y-%m-%d %H:%M'),
            bar_time=int(ctx.current_time),
            action=action,
            reason=reason,
            price=round(price, 2),
            quantity=round(quantity, 6),
            regime=regime.value,
            rsi=round(rsi_val, 1),
            atr_pct=round(atr_pct, 2),
            equity=round(ctx.equity, 2),
            pnl=round(self.risk_state.total_pnl, 2),
        )
        self.signals.append(signal)

    def _take_snapshot(self, ctx: StrategyContext):
        """保存快照"""
        pos = ctx.position
        snap = PaperTradingSnapshot(
            timestamp=datetime.fromtimestamp(ctx.current_time / 1000).strftime('%Y-%m-%d %H:%M'),
            equity=round(ctx.equity, 2),
            capital=round(ctx.capital, 2),
            position_value=round(pos.size * pos.entry_price if pos.is_open else 0, 2),
            position_side=pos.side,
            position_size=round(pos.size, 6),
            position_entry=round(pos.entry_price, 2),
            total_trades=len([t for t in ctx.trades if t.side in ('sell', 'cover')]),
            winning_trades=len([t for t in ctx.trades if t.side in ('sell', 'cover') and t.pnl > 0]),
            total_pnl=round(self.risk_state.total_pnl, 2),
            daily_pnl=round(self.risk_state.daily_pnl, 2),
            circuit_breaker=self.risk_state.circuit_breaker.value,
            last_signal=self.signals[-1].reason if self.signals else '',
        )
        self.snapshots.append(snap)


# ============================================
# 压力测试
# ============================================

def stress_test(
    strategy_name: str = 'adaptive_bollinger',
    symbol: str = 'BTC/USDT',
    timeframe: str = '4h',
    scenarios: List[str] = None,
) -> Dict[str, Any]:
    """
    压力测试 — 在历史极端行情上验证策略表现

    内置场景:
    1. 全周期: 包含牛熊的完整周期
    2. 暴跌月: 选取历史最大跌幅月份
    3. 快速反弹: V型反转行情
    """
    if scenarios is None:
        scenarios = ['full_period', 'recent_90d', 'recent_30d']

    engine_class = PaperTradingEngine
    results = {}

    # 场景1: 全周期
    if 'full_period' in scenarios:
        engine = engine_class(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            initial_capital=10000,
            stop_loss=0.05,
        )
        r = engine.run_simulation(days_back=365 * 2)
        results['full_period_2yr'] = r

    # 场景2: 最近90天
    if 'recent_90d' in scenarios:
        engine = engine_class(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            initial_capital=10000,
            stop_loss=0.05,
        )
        r = engine.run_simulation(days_back=90)
        results['recent_90d'] = r

    # 场景3: 最近30天
    if 'recent_30d' in scenarios:
        engine = engine_class(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            initial_capital=10000,
            stop_loss=0.05,
        )
        r = engine.run_simulation(days_back=30)
        results['recent_30d'] = r

    return results


# 全局实例
paper_engine = PaperTradingEngine()
