"""
增强版回测框架 v2
=================
核心特性:
  1. 优先读本地 SQLite，不依赖交易所 API
  2. 支持做多/做空/双向
  3. 仓位按资金百分比管理
  4. 内置止盈止损
  5. 完整绩效指标 (Sharpe/Sortino/Calmar/最大回撤天数/月度收益等)
  6. 纯函数式策略定义，安全且易测试
  7. 技术指标库原生集成

使用方式:
    from app.services.strategy_backtest import Backtest, BacktestConfig

    def my_strategy(ctx):
        if ctx.indicators['sma_fast'][-1] > ctx.indicators['sma_slow'][-1]:
            ctx.buy(percent=0.95)
        else:
            ctx.sell_all()

    config = BacktestConfig(
        exchange='okx', symbol='BTC/USDT', timeframe='1d',
        start_date='2024-01-01', end_date='2025-12-31',
    )
    result = Backtest(config, my_strategy).run()
    result.print_summary()
"""
import numpy as np
import logging
from typing import Dict, List, Optional, Callable, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, field

from app.db.local_db import db_instance as db
from app.services.indicators import (
    SMA, EMA, RSI, MACD, BBANDS, ATR, KDJ, OBV,
    CROSS_ABOVE, CROSS_BELOW, HIGHEST, LOWEST,
    klines_to_arrays, STOCH_RSI, VOLATILITY, VWAP,
    WMA, PERCENT_RANK,
)

logger = logging.getLogger(__name__)


# ============================================
# 配置
# ============================================

@dataclass
class BacktestConfig:
    """回测配置"""
    exchange: str = 'okx'
    symbol: str = 'BTC/USDT'
    timeframe: str = '1d'
    start_date: str = '2024-01-01'
    end_date: str = '2025-12-31'

    initial_capital: float = 10000.0       # 初始资金 (USDT)
    commission: float = 0.0004             # 手续费率 (万四 = OKX maker)
    slippage: float = 0.0001               # 滑点 (万一)
    allow_short: bool = False              # 是否允许做空
    max_leverage: float = 1.0              # 最大杠杆 (1=现货, >1=合约)

    # 全局风控
    stop_loss: Optional[float] = None      # 全局止损百分比 (0.05 = 5%)
    take_profit: Optional[float] = None    # 全局止盈百分比 (0.10 = 10%)
    trailing_stop: Optional[float] = None  # 追踪止损百分比

    # 指标配置 (策略需要的指标在这里声明)
    indicators_config: Dict[str, Any] = field(default_factory=dict)


# ============================================
# 交易方向 & 持仓
# ============================================

class Side:
    LONG = 'long'
    SHORT = 'short'


@dataclass
class Position:
    """持仓信息"""
    side: str = ''            # long / short / ''(空仓)
    size: float = 0.0         # 持仓数量 (币)
    entry_price: float = 0.0  # 开仓均价
    entry_time: int = 0       # 开仓时间戳
    highest_price: float = 0.0  # 持仓期间最高价 (追踪止损用)
    lowest_price: float = 999999999.0  # 持仓期间最低价

    @property
    def is_open(self) -> bool:
        return self.size > 0 and self.side != ''

    @property
    def value(self) -> float:
        return self.size * self.entry_price


@dataclass
class TradeRecord:
    """交易记录"""
    timestamp: int
    side: str           # buy / sell / short / cover
    price: float
    quantity: float
    value: float        # = price * quantity
    fee: float
    pnl: float = 0.0   # 平仓盈亏
    pnl_pct: float = 0.0  # 平仓盈亏百分比
    bar_index: int = 0
    reason: str = ''    # 开仓原因: signal / stop_loss / take_profit / trailing_stop


# ============================================
# 策略上下文 (策略函数的参数)
# ============================================

class StrategyContext:
    """
    策略上下文 — 策略函数通过此对象访问数据和下单
    """

    def __init__(self, config: BacktestConfig):
        self.config = config

        # K线数据 (numpy arrays)
        self.timestamp: np.ndarray = np.array([])
        self.open: np.ndarray = np.array([])
        self.high: np.ndarray = np.array([])
        self.low: np.ndarray = np.array([])
        self.close: np.ndarray = np.array([])
        self.volume: np.ndarray = np.array([])

        # 预计算的技术指标
        self.indicators: Dict[str, np.ndarray] = {}

        # 当前 bar 索引
        self.bar_index: int = 0

        # 账户状态
        self.capital: float = config.initial_capital
        self.position: Position = Position()
        self.equity: float = config.initial_capital

        # 交易记录
        self.trades: List[TradeRecord] = []

        # 内部状态
        self._pending_orders: List[dict] = []

    # ------ 价格访问快捷方式 ------

    @property
    def current_price(self) -> float:
        return float(self.close[self.bar_index])

    @property
    def current_time(self) -> int:
        return int(self.timestamp[self.bar_index])

    @property
    def bars_count(self) -> int:
        return self.bar_index + 1

    # ------ 下单接口 ------

    def buy(self, quantity: float = 0, percent: float = 0, reason: str = 'signal'):
        """
        买入开多
        Args:
            quantity: 买入数量 (币)，与 percent 二选一
            percent: 按可用资金百分比买入 (0~1)，如 0.95 = 95%资金
            reason: 交易原因
        """
        if self.position.is_open and self.position.side == Side.SHORT:
            # 先平空再开多
            self._close_position(reason='reverse_to_long')

        price = self.current_price
        if percent > 0:
            available = self.capital * self.config.max_leverage
            quantity = (available * percent) / (price * (1 + self.config.commission + self.config.slippage))

        if quantity <= 0:
            return

        exec_price = price * (1 + self.config.slippage)
        cost = exec_price * quantity
        fee = cost * self.config.commission

        if cost + fee > self.capital * self.config.max_leverage:
            # 资金不足，调整数量
            available = self.capital * self.config.max_leverage
            quantity = available / (exec_price * (1 + self.config.commission))
            cost = exec_price * quantity
            fee = cost * self.config.commission

        if quantity <= 0:
            return

        self.capital -= (cost + fee)
        self.position = Position(
            side=Side.LONG,
            size=quantity,
            entry_price=exec_price,
            entry_time=self.current_time,
            highest_price=exec_price,
            lowest_price=exec_price,
        )

        self.trades.append(TradeRecord(
            timestamp=self.current_time,
            side='buy',
            price=exec_price,
            quantity=quantity,
            value=cost,
            fee=fee,
            bar_index=self.bar_index,
            reason=reason,
        ))

    def sell(self, quantity: float = 0, percent: float = 0, reason: str = 'signal'):
        """卖出平多 (部分或全部)"""
        if not self.position.is_open or self.position.side != Side.LONG:
            return

        if percent > 0:
            quantity = self.position.size * percent
        elif quantity <= 0:
            quantity = self.position.size

        quantity = min(quantity, self.position.size)
        if quantity <= 0:
            return

        self._execute_sell(quantity, reason)

    def sell_all(self, reason: str = 'signal'):
        """全部平仓"""
        if self.position.is_open:
            self._close_position(reason)

    def short(self, quantity: float = 0, percent: float = 0, reason: str = 'signal'):
        """做空"""
        if not self.config.allow_short:
            return

        if self.position.is_open and self.position.side == Side.LONG:
            self._close_position(reason='reverse_to_short')

        price = self.current_price
        if percent > 0:
            available = self.capital * self.config.max_leverage
            quantity = (available * percent) / (price * (1 + self.config.commission + self.config.slippage))

        if quantity <= 0:
            return

        exec_price = price * (1 - self.config.slippage)
        value = exec_price * quantity
        fee = value * self.config.commission

        # 做空保证金
        margin = value / self.config.max_leverage
        if margin + fee > self.capital:
            available = self.capital
            margin = available / (1 + self.config.commission)
            quantity = margin * self.config.max_leverage / exec_price
            value = exec_price * quantity
            fee = value * self.config.commission
            margin = value / self.config.max_leverage

        if quantity <= 0:
            return

        self.capital -= fee  # 做空只扣手续费，保证金冻结在仓位里
        self.position = Position(
            side=Side.SHORT,
            size=quantity,
            entry_price=exec_price,
            entry_time=self.current_time,
            highest_price=exec_price,
            lowest_price=exec_price,
        )

        self.trades.append(TradeRecord(
            timestamp=self.current_time,
            side='short',
            price=exec_price,
            quantity=quantity,
            value=value,
            fee=fee,
            bar_index=self.bar_index,
            reason=reason,
        ))

    def cover(self, quantity: float = 0, percent: float = 0, reason: str = 'signal'):
        """平空"""
        if not self.position.is_open or self.position.side != Side.SHORT:
            return
        if percent > 0:
            quantity = self.position.size * percent
        elif quantity <= 0:
            quantity = self.position.size
        quantity = min(quantity, self.position.size)
        if quantity <= 0:
            return
        self._execute_cover(quantity, reason)

    # ------ 内部执行 ------

    def _execute_sell(self, quantity: float, reason: str):
        """执行卖出 (平多)"""
        exec_price = self.current_price * (1 - self.config.slippage)
        proceeds = exec_price * quantity
        fee = proceeds * self.config.commission
        pnl = (exec_price - self.position.entry_price) * quantity - fee
        pnl_pct = (exec_price / self.position.entry_price - 1) * 100

        self.capital += (proceeds - fee)
        self.position.size -= quantity

        if self.position.size <= 1e-10:
            self.position = Position()

        self.trades.append(TradeRecord(
            timestamp=self.current_time,
            side='sell',
            price=exec_price,
            quantity=quantity,
            value=proceeds,
            fee=fee,
            pnl=pnl,
            pnl_pct=pnl_pct,
            bar_index=self.bar_index,
            reason=reason,
        ))

    def _execute_cover(self, quantity: float, reason: str):
        """执行平空"""
        exec_price = self.current_price * (1 + self.config.slippage)
        value = exec_price * quantity
        fee = value * self.config.commission
        # 空头盈亏 = (开仓价 - 平仓价) * 数量
        pnl = (self.position.entry_price - exec_price) * quantity - fee
        pnl_pct = (self.position.entry_price / exec_price - 1) * 100

        self.capital += pnl  # 空头PnL直接加回资金
        self.position.size -= quantity

        if self.position.size <= 1e-10:
            self.position = Position()

        self.trades.append(TradeRecord(
            timestamp=self.current_time,
            side='cover',
            price=exec_price,
            quantity=quantity,
            value=value,
            fee=fee,
            pnl=pnl,
            pnl_pct=pnl_pct,
            bar_index=self.bar_index,
            reason=reason,
        ))

    def _close_position(self, reason: str = 'signal'):
        """完全平仓"""
        if not self.position.is_open:
            return
        if self.position.side == Side.LONG:
            self._execute_sell(self.position.size, reason)
        elif self.position.side == Side.SHORT:
            self._execute_cover(self.position.size, reason)


# ============================================
# 回测结果
# ============================================

@dataclass
class BacktestResultV2:
    """回测结果 v2"""
    config: BacktestConfig

    # 资金曲线
    equity_curve: np.ndarray = field(default_factory=lambda: np.array([]))
    timestamps: np.ndarray = field(default_factory=lambda: np.array([]))

    # 交易记录
    trades: List[TradeRecord] = field(default_factory=list)

    # ---- 绩效指标 ----
    initial_capital: float = 0
    final_equity: float = 0
    total_return_pct: float = 0       # 总收益率 %
    annual_return_pct: float = 0      # 年化收益率 %
    max_drawdown_pct: float = 0       # 最大回撤 %
    max_drawdown_duration_days: int = 0  # 最大回撤持续天数
    sharpe_ratio: float = 0           # 夏普比率
    sortino_ratio: float = 0          # Sortino 比率
    calmar_ratio: float = 0           # Calmar 比率
    win_rate_pct: float = 0           # 胜率 %
    profit_factor: float = 0          # 盈亏比
    avg_win_pct: float = 0            # 平均盈利 %
    avg_loss_pct: float = 0           # 平均亏损 %
    max_consecutive_wins: int = 0     # 最大连胜
    max_consecutive_losses: int = 0   # 最大连亏
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    largest_win: float = 0
    largest_loss: float = 0
    total_fees: float = 0
    avg_holding_bars: float = 0       # 平均持仓K线数
    expectancy: float = 0             # 期望收益 = 胜率*平均盈利 - 败率*平均亏损

    # 月度收益
    monthly_returns: Dict[str, float] = field(default_factory=dict)

    # 状态
    status: str = 'completed'
    error_message: str = ''
    elapsed_seconds: float = 0
    total_bars: int = 0

    def print_summary(self):
        """打印回测摘要"""
        print(f"\n{'='*60}")
        print(f"  回测报告: {self.config.symbol} {self.config.timeframe}")
        print(f"  {self.config.start_date} ~ {self.config.end_date}")
        print(f"{'='*60}")
        print(f"  初始资金:     ${self.initial_capital:,.2f}")
        print(f"  最终权益:     ${self.final_equity:,.2f}")
        print(f"  总收益率:     {self.total_return_pct:+.2f}%")
        print(f"  年化收益率:   {self.annual_return_pct:+.2f}%")
        print(f"  最大回撤:     {self.max_drawdown_pct:.2f}%")
        print(f"  回撤持续:     {self.max_drawdown_duration_days} 天")
        print(f"  夏普比率:     {self.sharpe_ratio:.3f}")
        print(f"  Sortino:      {self.sortino_ratio:.3f}")
        print(f"  Calmar:       {self.calmar_ratio:.3f}")
        print(f"  {'─'*58}")
        print(f"  总交易次数:   {self.total_trades}")
        print(f"  胜率:         {self.win_rate_pct:.1f}%")
        print(f"  盈亏比:       {self.profit_factor:.2f}")
        print(f"  平均盈利:     {self.avg_win_pct:+.2f}%")
        print(f"  平均亏损:     {self.avg_loss_pct:+.2f}%")
        print(f"  期望收益:     ${self.expectancy:,.2f}/笔")
        print(f"  最大连胜:     {self.max_consecutive_wins}")
        print(f"  最大连亏:     {self.max_consecutive_losses}")
        print(f"  总手续费:     ${self.total_fees:,.2f}")
        print(f"  平均持仓:     {self.avg_holding_bars:.1f} bars")
        print(f"  {'─'*58}")
        print(f"  数据条数:     {self.total_bars}")
        print(f"  耗时:         {self.elapsed_seconds:.2f}s")
        print(f"{'='*60}")

        if self.monthly_returns:
            print(f"\n  月度收益:")
            for month, ret in sorted(self.monthly_returns.items()):
                bar = '█' * int(abs(ret) / 2) if abs(ret) > 0 else ''
                sign = '+' if ret >= 0 else ''
                print(f"    {month}: {sign}{ret:.2f}% {bar}")
            print()


# ============================================
# 回测引擎 v2
# ============================================

class Backtest:
    """
    回测引擎 v2

    Args:
        config: 回测配置
        strategy: 策略函数 — def strategy(ctx: StrategyContext)
        setup_indicators: 指标初始化函数 — def setup(ctx: StrategyContext)
    """

    def __init__(self, config: BacktestConfig,
                 strategy: Callable[[StrategyContext], None],
                 setup_indicators: Callable[[StrategyContext], None] = None):
        self.config = config
        self.strategy_fn = strategy
        self.setup_indicators_fn = setup_indicators

    def run(self) -> BacktestResultV2:
        """执行回测"""
        start_time = datetime.now()
        result = BacktestResultV2(
            config=self.config,
            initial_capital=self.config.initial_capital,
        )

        try:
            # 1. 加载数据
            klines = self._load_data()
            if not klines:
                raise ValueError(
                    f"没有找到本地数据: {self.config.exchange} {self.config.symbol} {self.config.timeframe} "
                    f"({self.config.start_date} ~ {self.config.end_date}). "
                    f"请先运行数据同步: POST /api/v1/data_sync/sync_one"
                )

            # 2. 转为 numpy arrays
            arrays = klines_to_arrays(klines)

            # 3. 初始化上下文
            ctx = StrategyContext(self.config)
            ctx.timestamp = arrays['timestamp']
            ctx.open = arrays['open']
            ctx.high = arrays['high']
            ctx.low = arrays['low']
            ctx.close = arrays['close']
            ctx.volume = arrays['volume']

            # 4. 计算技术指标
            self._setup_default_indicators(ctx)
            if self.setup_indicators_fn:
                self.setup_indicators_fn(ctx)

            total_bars = len(ctx.close)
            logger.info(f"回测开始: {self.config.symbol} {self.config.timeframe}, {total_bars} bars")

            # 5. 遍历每根 K线
            equity_curve = np.zeros(total_bars)

            for i in range(total_bars):
                ctx.bar_index = i

                # 更新持仓追踪价格
                if ctx.position.is_open:
                    price = ctx.current_price
                    ctx.position.highest_price = max(ctx.position.highest_price, price)
                    ctx.position.lowest_price = min(ctx.position.lowest_price, price)

                # 检查全局止损/止盈/追踪止损
                self._check_risk_management(ctx)

                # 调用策略
                self.strategy_fn(ctx)

                # 计算当前权益
                if ctx.position.is_open:
                    if ctx.position.side == Side.LONG:
                        pos_value = ctx.position.size * ctx.current_price
                        equity_curve[i] = ctx.capital + pos_value
                    else:  # SHORT
                        unrealized_pnl = (ctx.position.entry_price - ctx.current_price) * ctx.position.size
                        equity_curve[i] = ctx.capital + ctx.position.value + unrealized_pnl
                else:
                    equity_curve[i] = ctx.capital

            # 6. 最终平仓
            if ctx.position.is_open:
                ctx.bar_index = total_bars - 1
                ctx._close_position('end_of_backtest')

            # 7. 生成结果
            result.equity_curve = equity_curve
            result.timestamps = ctx.timestamp
            result.trades = ctx.trades
            result.final_equity = equity_curve[-1] if len(equity_curve) > 0 else self.config.initial_capital
            result.total_bars = total_bars

            # 8. 计算绩效指标
            self._calculate_metrics(result)

            elapsed = (datetime.now() - start_time).total_seconds()
            result.elapsed_seconds = elapsed
            result.status = 'completed'

            logger.info(
                f"回测完成: {result.total_return_pct:+.2f}% | "
                f"Sharpe {result.sharpe_ratio:.2f} | "
                f"MaxDD {result.max_drawdown_pct:.1f}% | "
                f"{result.total_trades} trades | {elapsed:.2f}s"
            )

        except Exception as e:
            logger.error(f"回测失败: {e}")
            result.status = 'failed'
            result.error_message = str(e)
            result.elapsed_seconds = (datetime.now() - start_time).total_seconds()

        return result

    # ============================================
    # 数据加载 (优先读本地 DB，不足时从交易所拉取)
    # ============================================

    # 时间周期对应的毫秒数
    TIMEFRAME_MS = {
        '1m': 60 * 1000,
        '5m': 5 * 60 * 1000,
        '15m': 15 * 60 * 1000,
        '30m': 30 * 60 * 1000,
        '1h': 60 * 60 * 1000,
        '4h': 4 * 60 * 60 * 1000,
        '1d': 24 * 60 * 60 * 1000,
        '1w': 7 * 24 * 60 * 60 * 1000,
    }

    def _load_data(self) -> List[Dict]:
        """
        加载历史K线数据:
        1. 先查本地 SQLite
        2. 如果本地数据不足，从交易所实时拉取并缓存到 DB
        3. 重新从 DB 读取完整数据
        """
        start_ts = int(datetime.strptime(self.config.start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ts = int(datetime.strptime(self.config.end_date, "%Y-%m-%d").timestamp() * 1000)

        # 1. 先查本地
        klines = db.get_klines(
            exchange=self.config.exchange,
            symbol=self.config.symbol,
            timeframe=self.config.timeframe,
            limit=999999,
            start=start_ts,
            end=end_ts,
        )

        # 2. 判断数据是否充足 — 估算理论K线条数
        interval_ms = self.TIMEFRAME_MS.get(self.config.timeframe, 3600000)
        expected_bars = (end_ts - start_ts) // interval_ms
        # 如果本地数据不足理论值的 80%，则认为需要从交易所补充
        coverage = len(klines) / max(expected_bars, 1)

        if coverage < 0.8:
            logger.info(
                f"本地数据不足: 预期约 {expected_bars} 条，实际 {len(klines)} 条 "
                f"(覆盖率 {coverage:.0%})。开始从交易所拉取..."
            )
            self._fetch_and_cache_klines(start_ts, end_ts, interval_ms)

            # 重新从 DB 读取
            klines = db.get_klines(
                exchange=self.config.exchange,
                symbol=self.config.symbol,
                timeframe=self.config.timeframe,
                limit=999999,
                start=start_ts,
                end=end_ts,
            )

        logger.info(
            f"K线数据就绪: {self.config.exchange} {self.config.symbol} {self.config.timeframe}: "
            f"{len(klines)} 条 ({self.config.start_date} ~ {self.config.end_date})"
        )
        return klines

    def _fetch_and_cache_klines(self, start_ts: int, end_ts: int, interval_ms: int):
        """
        从交易所分批拉取K线并存入本地 DB
        使用 CCXT 同步 API，适合在回测场景中调用
        """
        import time
        from app.exchange import exchange_manager

        exchange = exchange_manager.get_exchange(self.config.exchange)
        if not exchange:
            raise ValueError(
                f"交易所 {self.config.exchange} 不可用，无法自动拉取数据。"
                f"请先配置交易所或手动同步数据。"
            )

        symbol = self.config.symbol
        timeframe = self.config.timeframe
        current_ms = start_ts
        total_fetched = 0
        batch_size = 500  # 每批拉取数量

        logger.info(
            f"[自动数据拉取] {self.config.exchange} {symbol} {timeframe} "
            f"从 {datetime.fromtimestamp(start_ts/1000).strftime('%Y-%m-%d')} "
            f"到 {datetime.fromtimestamp(end_ts/1000).strftime('%Y-%m-%d')}"
        )

        while current_ms < end_ts:
            try:
                klines = exchange.fetch_ohlcv(
                    symbol, timeframe,
                    limit=batch_size,
                    since=current_ms
                )

                if not klines:
                    logger.debug(f"无更多数据，停止拉取")
                    break

                # 过滤超出结束时间的数据
                klines = [k for k in klines if k['timestamp'] <= end_ts]
                if not klines:
                    break

                # 写入本地数据库
                inserted = db.insert_klines(
                    self.config.exchange, symbol, timeframe, klines
                )
                total_fetched += len(klines)

                # 推进游标
                last_ts = klines[-1]['timestamp']
                current_ms = last_ts + interval_ms

                # 进度日志（每 5 批输出一次）
                if total_fetched % (batch_size * 5) < batch_size:
                    logger.info(
                        f"[自动数据拉取] 已获取 {total_fetched} 条 "
                        f"(到 {datetime.fromtimestamp(last_ts/1000).strftime('%Y-%m-%d %H:%M')})"
                    )

                # 避免触发 API 限流
                time.sleep(0.3)

            except Exception as e:
                logger.warning(f"[自动数据拉取] 拉取失败: {e}，等待后重试...")
                time.sleep(2)
                continue

        logger.info(f"[自动数据拉取] 完成，共获取 {total_fetched} 条K线数据")

    # ============================================
    # 指标初始化
    # ============================================

    def _setup_default_indicators(self, ctx: StrategyContext):
        """设置默认指标 — 常用的都预计算好"""
        c = ctx.close
        h = ctx.high
        lo = ctx.low
        v = ctx.volume

        # 均线
        ctx.indicators['sma_7'] = SMA(c, 7)
        ctx.indicators['sma_25'] = SMA(c, 25)
        ctx.indicators['sma_50'] = SMA(c, 50)
        ctx.indicators['sma_200'] = SMA(c, 200)
        ctx.indicators['ema_12'] = EMA(c, 12)
        ctx.indicators['ema_26'] = EMA(c, 26)

        # MACD
        macd_line, signal_line, histogram = MACD(c)
        ctx.indicators['macd'] = macd_line
        ctx.indicators['macd_signal'] = signal_line
        ctx.indicators['macd_hist'] = histogram

        # RSI
        ctx.indicators['rsi_14'] = RSI(c, 14)
        ctx.indicators['rsi_7'] = RSI(c, 7)

        # 布林带
        bb_upper, bb_middle, bb_lower = BBANDS(c, 20, 2.0)
        ctx.indicators['bb_upper'] = bb_upper
        ctx.indicators['bb_middle'] = bb_middle
        ctx.indicators['bb_lower'] = bb_lower

        # ATR
        ctx.indicators['atr_14'] = ATR(h, lo, c, 14)

        # KDJ
        k, d, j = KDJ(h, lo, c)
        ctx.indicators['kdj_k'] = k
        ctx.indicators['kdj_d'] = d
        ctx.indicators['kdj_j'] = j

        # OBV
        ctx.indicators['obv'] = OBV(c, v)

    # ============================================
    # 风控检查
    # ============================================

    def _check_risk_management(self, ctx: StrategyContext):
        """检查止损/止盈/追踪止损"""
        if not ctx.position.is_open:
            return

        price = ctx.current_price
        entry = ctx.position.entry_price
        side = ctx.position.side

        if side == Side.LONG:
            pnl_pct = (price - entry) / entry

            # 止损
            if self.config.stop_loss and pnl_pct <= -self.config.stop_loss:
                ctx._close_position('stop_loss')
                return

            # 止盈
            if self.config.take_profit and pnl_pct >= self.config.take_profit:
                ctx._close_position('take_profit')
                return

            # 追踪止损
            if self.config.trailing_stop:
                highest = ctx.position.highest_price
                drawdown_from_high = (highest - price) / highest
                if drawdown_from_high >= self.config.trailing_stop:
                    ctx._close_position('trailing_stop')
                    return

        elif side == Side.SHORT:
            pnl_pct = (entry - price) / entry

            if self.config.stop_loss and pnl_pct <= -self.config.stop_loss:
                ctx._close_position('stop_loss')
                return

            if self.config.take_profit and pnl_pct >= self.config.take_profit:
                ctx._close_position('take_profit')
                return

            if self.config.trailing_stop:
                lowest = ctx.position.lowest_price
                if lowest > 0:
                    rise_from_low = (price - lowest) / lowest
                    if rise_from_low >= self.config.trailing_stop:
                        ctx._close_position('trailing_stop')
                        return

    # ============================================
    # 绩效计算
    # ============================================

    def _calculate_metrics(self, result: BacktestResultV2):
        """计算完整绩效指标"""
        equity = result.equity_curve
        initial = result.initial_capital
        final = result.final_equity

        if len(equity) < 2:
            return

        # ---- 收益率 ----
        result.total_return_pct = (final - initial) / initial * 100

        start_ts = result.timestamps[0]
        end_ts = result.timestamps[-1]
        days = max((end_ts - start_ts) / (1000 * 86400), 1)
        years = days / 365.0

        if years > 0 and (1 + result.total_return_pct / 100) > 0:
            result.annual_return_pct = ((1 + result.total_return_pct / 100) ** (1 / years) - 1) * 100
        else:
            result.annual_return_pct = 0

        # ---- 最大回撤 & 回撤持续天数 ----
        peak = equity[0]
        max_dd = 0
        dd_start_idx = 0
        max_dd_duration = 0
        current_dd_start = 0

        for i in range(len(equity)):
            if equity[i] > peak:
                peak = equity[i]
                # 回撤恢复
                if current_dd_start > 0:
                    duration_ms = result.timestamps[i] - result.timestamps[current_dd_start]
                    duration_days = duration_ms / (1000 * 86400)
                    max_dd_duration = max(max_dd_duration, int(duration_days))
                current_dd_start = i

            dd = (peak - equity[i]) / peak * 100
            if dd > max_dd:
                max_dd = dd
                dd_start_idx = current_dd_start

        result.max_drawdown_pct = max_dd

        # 如果回测结束时还在回撤中
        if equity[-1] < peak:
            duration_ms = result.timestamps[-1] - result.timestamps[current_dd_start]
            max_dd_duration = max(max_dd_duration, int(duration_ms / (1000 * 86400)))

        result.max_drawdown_duration_days = max_dd_duration

        # ---- 收益率序列 ----
        returns = np.diff(equity) / equity[:-1]
        returns = returns[~np.isnan(returns)]

        if len(returns) == 0:
            return

        # 根据 timeframe 确定年化系数
        tf_annual = {
            '1m': 525600, '5m': 105120, '15m': 35040, '30m': 17520,
            '1h': 8760, '4h': 2190, '1d': 365, '1w': 52,
        }
        annual_factor = tf_annual.get(self.config.timeframe, 365)

        avg_return = np.mean(returns)
        std_return = np.std(returns, ddof=1)

        # ---- 夏普比率 ----
        if std_return > 0:
            result.sharpe_ratio = (avg_return * annual_factor) / (std_return * np.sqrt(annual_factor))
        else:
            result.sharpe_ratio = 0

        # ---- Sortino 比率 ----
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0:
            downside_std = np.std(downside_returns, ddof=1)
            if downside_std > 0:
                result.sortino_ratio = (avg_return * annual_factor) / (downside_std * np.sqrt(annual_factor))

        # ---- Calmar 比率 ----
        if result.max_drawdown_pct > 0:
            result.calmar_ratio = result.annual_return_pct / result.max_drawdown_pct

        # ---- 交易统计 ----
        close_trades = [t for t in result.trades if t.side in ('sell', 'cover')]
        result.total_trades = len(close_trades)
        result.total_fees = sum(t.fee for t in result.trades)

        wins = [t for t in close_trades if t.pnl > 0]
        losses = [t for t in close_trades if t.pnl < 0]
        result.winning_trades = len(wins)
        result.losing_trades = len(losses)

        if result.total_trades > 0:
            result.win_rate_pct = len(wins) / result.total_trades * 100

        total_win = sum(t.pnl for t in wins)
        total_loss = abs(sum(t.pnl for t in losses))

        if wins:
            result.avg_win_pct = np.mean([t.pnl_pct for t in wins])
            result.largest_win = max(t.pnl for t in wins)
        if losses:
            result.avg_loss_pct = np.mean([t.pnl_pct for t in losses])
            result.largest_loss = min(t.pnl for t in losses)

        if total_loss > 0:
            result.profit_factor = total_win / total_loss

        # 期望收益
        if result.total_trades > 0:
            result.expectancy = sum(t.pnl for t in close_trades) / result.total_trades

        # ---- 最大连胜/连亏 ----
        if close_trades:
            streak = 0
            max_win_streak = 0
            max_loss_streak = 0
            for t in close_trades:
                if t.pnl > 0:
                    if streak > 0:
                        streak += 1
                    else:
                        streak = 1
                    max_win_streak = max(max_win_streak, streak)
                elif t.pnl < 0:
                    if streak < 0:
                        streak -= 1
                    else:
                        streak = -1
                    max_loss_streak = max(max_loss_streak, abs(streak))
                else:
                    streak = 0

            result.max_consecutive_wins = max_win_streak
            result.max_consecutive_losses = max_loss_streak

        # ---- 平均持仓 K 线数 ----
        open_trades = [t for t in result.trades if t.side in ('buy', 'short')]
        if open_trades and close_trades and len(open_trades) == len(close_trades):
            holding_bars = [
                close_trades[i].bar_index - open_trades[i].bar_index
                for i in range(len(close_trades))
            ]
            result.avg_holding_bars = np.mean(holding_bars) if holding_bars else 0

        # ---- 月度收益 ----
        self._calculate_monthly_returns(result)

    def _calculate_monthly_returns(self, result: BacktestResultV2):
        """计算月度收益"""
        if len(result.equity_curve) < 2:
            return

        monthly = {}
        prev_equity = result.equity_curve[0]
        prev_month = datetime.fromtimestamp(result.timestamps[0] / 1000).strftime('%Y-%m')

        for i in range(1, len(result.equity_curve)):
            dt = datetime.fromtimestamp(result.timestamps[i] / 1000)
            current_month = dt.strftime('%Y-%m')

            if current_month != prev_month:
                # 月份切换，记录上个月的收益
                current_equity = result.equity_curve[i - 1]
                if prev_equity > 0:
                    monthly[prev_month] = (current_equity - prev_equity) / prev_equity * 100
                prev_equity = current_equity
                prev_month = current_month

        # 最后一个月
        final_equity = result.equity_curve[-1]
        if prev_equity > 0:
            monthly[prev_month] = (final_equity - prev_equity) / prev_equity * 100

        result.monthly_returns = monthly
