"""
Phase 3 高级策略库
==================
包含:
  1. 自适应布林带策略 — 根据市场状态动态调整参数
  2. 趋势跟踪策略 — 专门处理趋势行情
  3. 多策略组合引擎 — 根据市场状态切换策略 + 动态仓位
  4. 动态仓位管理器 — 基于波动率的仓位大小调整

使用方式:
    from app.services.pro_strategies import (
        adaptive_bollinger_strategy, adaptive_bollinger_setup,
        trend_following_strategy, trend_following_setup,
        combo_strategy, combo_strategy_setup,
    )
    from app.services.strategy_backtest import Backtest, BacktestConfig

    config = BacktestConfig(
        exchange='okx', symbol='BTC/USDT', timeframe='4h',
        start_date='2024-03-01', end_date='2026-01-31',
        stop_loss=0.05,
    )
    result = Backtest(config, combo_strategy, combo_strategy_setup).run()
"""
import numpy as np
from typing import Dict, Any, Callable
from app.services.indicators import (
    SMA, EMA, RSI, BBANDS, ATR, MACD, CROSS_ABOVE, CROSS_BELOW,
    HIGHEST, LOWEST, VOLATILITY,
)
from app.services.market_regime import (
    MarketRegime, detect_regime, setup_regime_indicators, ADX,
)
from app.services.strategy_backtest import StrategyContext


# ============================================
# 工具: 动态仓位管理
# ============================================

def calculate_position_size(ctx: StrategyContext, bar_index: int,
                            base_pct: float = 0.90,
                            risk_per_trade: float = 0.03,
                            ) -> float:
    """
    基于ATR的动态仓位管理 (v2 — 更积极)
    
    原理:
      波动大时仓位适当减小，波动小时仓位加大。
      每笔交易风险控制在总资金的 risk_per_trade (默认3%)。
      确保仓位不会过小而无法捕捉收益。
    
    公式:
      position_size = (资金 × 风险比例) / (ATR × ATR倍数)
      仓位百分比 = clamp(position_size / 总资金, 0.30, base_pct)
    """
    i = bar_index
    atr = ctx.indicators.get('atr_14')
    if atr is None or np.isnan(atr[i]):
        return base_pct * 0.7  # 没有ATR数据时用70%仓位

    price = ctx.current_price
    atr_val = atr[i]
    
    if atr_val <= 0 or price <= 0:
        return base_pct * 0.7

    # 风险金额 = 总权益 * risk_per_trade
    risk_amount = ctx.equity * risk_per_trade
    
    # 止损距离 = 2 * ATR
    stop_distance = 2.0 * atr_val
    
    # 可买数量 = 风险金额 / 止损距离
    qty = risk_amount / stop_distance
    
    # 转为百分比
    position_value = qty * price
    pct = position_value / ctx.equity if ctx.equity > 0 else 0
    
    # 限制范围: 最低30%仓位，确保能捕捉收益
    return max(0.30, min(pct, base_pct))


def check_consecutive_losses(ctx: StrategyContext, max_losses: int = 3) -> bool:
    """
    检查是否连续亏损超过阈值 — 如果是，暂停交易
    极端行情保护机制
    """
    close_trades = [t for t in ctx.trades if t.side in ('sell', 'cover')]
    if len(close_trades) < max_losses:
        return False
    
    recent = close_trades[-max_losses:]
    return all(t.pnl < 0 for t in recent)


# ============================================
# 策略 6: 自适应布林带 (Adaptive Bollinger)
# ============================================

def adaptive_bollinger_factory(params: Dict[str, Any]) -> Callable:
    """工厂函数: 创建自适应布林带策略"""
    def strategy(ctx: StrategyContext):
        adaptive_bollinger_strategy(ctx, params)
    return strategy


def adaptive_bollinger_setup_factory(params: Dict[str, Any]) -> Callable:
    """工厂函数: 创建指标初始化"""
    def setup(ctx: StrategyContext):
        adaptive_bollinger_setup(ctx, params)
    return setup


def adaptive_bollinger_setup(ctx: StrategyContext, params: Dict[str, Any] = None):
    """自适应布林带 — 指标初始化"""
    c = ctx.close
    h = ctx.high
    lo = ctx.low
    v = ctx.volume

    # 多组布林带（趋势/震荡用不同参数）
    # 趋势模式: 窄带快反应
    bb_trend_u, bb_trend_m, bb_trend_l = BBANDS(c, 15, 2.0)
    ctx.indicators['bb_trend_upper'] = bb_trend_u
    ctx.indicators['bb_trend_middle'] = bb_trend_m
    ctx.indicators['bb_trend_lower'] = bb_trend_l

    # 震荡模式: 宽带慢反应
    bb_range_u, bb_range_m, bb_range_l = BBANDS(c, 30, 2.5)
    ctx.indicators['bb_range_upper'] = bb_range_u
    ctx.indicators['bb_range_middle'] = bb_range_m
    ctx.indicators['bb_range_lower'] = bb_range_l

    # 市场状态指标
    regime_indicators = setup_regime_indicators(h, lo, c, v)
    for k, arr in regime_indicators.items():
        ctx.indicators[f'regime_{k}'] = arr

    # RSI 辅助
    ctx.indicators['rsi_14'] = RSI(c, 14)


def adaptive_bollinger_strategy(ctx: StrategyContext, params: Dict[str, Any] = None):
    """
    自适应布林带策略
    
    核心改进 (相对 Phase 2 的布林带):
    1. 根据市场状态自动切换布林带参数
    2. 趋势市: 窄带(15,2.0)，只做顺趋势方向
    3. 震荡市: 宽带(30,2.5)，双向均值回归
    4. 高波动: 减仓或不开新仓
    5. 动态仓位管理
    """
    i = ctx.bar_index
    if i < 50:
        return

    price = ctx.current_price

    # 检测市场状态
    regime = detect_regime(
        ctx.high, ctx.low, ctx.close, i,
        adx_arr=ctx.indicators.get('regime_adx'),
        plus_di_arr=ctx.indicators.get('regime_plus_di'),
        minus_di_arr=ctx.indicators.get('regime_minus_di'),
        vol_percentile_arr=ctx.indicators.get('regime_vol_percentile'),
        sma_slope_arr=ctx.indicators.get('regime_sma_slope'),
    )

    rsi = ctx.indicators['rsi_14'][i] if not np.isnan(ctx.indicators['rsi_14'][i]) else 50

    # 连续亏损保护 (宽松: 5次才触发，且只暂停不平仓)
    if check_consecutive_losses(ctx, max_losses=5):
        return  # 暂停开新仓，但不强制平仓

    # ===== 高波动: 仅当波动极端时才减仓，不完全停止 =====
    if regime == MarketRegime.HIGH_VOLATILITY:
        # 高波动仍然可以交易，但用更保守的方式
        # 用宽带布林带，仅在极端超卖时买入
        lower = ctx.indicators['bb_range_lower'][i]
        upper = ctx.indicators['bb_range_upper'][i]
        if not np.isnan(lower) and not np.isnan(upper):
            if not ctx.position.is_open and price <= lower and rsi < 25:
                pct = calculate_position_size(ctx, i) * 0.5  # 半仓
                ctx.buy(percent=pct, reason='high_vol_extreme_oversold')
            elif ctx.position.is_open and price >= upper:
                ctx.sell_all(reason='high_vol_tp')
        return

    # ===== 趋势行情 =====
    if regime in (MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN):
        upper = ctx.indicators['bb_trend_upper'][i]
        middle = ctx.indicators['bb_trend_middle'][i]
        lower = ctx.indicators['bb_trend_lower'][i]

        if np.isnan(upper) or np.isnan(lower):
            return

        if regime == MarketRegime.TRENDING_UP:
            # 上升趋势：回调到中轨或下轨附近买入
            if not ctx.position.is_open:
                if price <= lower and rsi < 45:
                    pct = calculate_position_size(ctx, i)
                    ctx.buy(percent=pct, reason='trend_up_bb_lower')
                elif price <= middle and rsi < 40:
                    pct = calculate_position_size(ctx, i) * 0.7
                    ctx.buy(percent=pct, reason='trend_up_pullback')
            # 突破上轨 + RSI超买 → 部分止盈
            elif ctx.position.is_open and price >= upper and rsi > 75:
                ctx.sell(percent=0.4, reason='trend_partial_tp')

        elif regime == MarketRegime.TRENDING_DOWN:
            # 下降趋势：依然可以做均值回归，但更严格
            if not ctx.position.is_open and price <= lower and rsi < 25:
                pct = calculate_position_size(ctx, i) * 0.5  # 半仓
                ctx.buy(percent=pct, reason='trend_down_oversold')
            elif ctx.position.is_open:
                if price >= middle:
                    ctx.sell_all(reason='trend_down_exit')

    # ===== 震荡行情 =====
    elif regime == MarketRegime.RANGING:
        upper = ctx.indicators['bb_range_upper'][i]
        middle = ctx.indicators['bb_range_middle'][i]
        lower = ctx.indicators['bb_range_lower'][i]

        if np.isnan(upper) or np.isnan(lower):
            return

        if not ctx.position.is_open:
            # 下轨买入
            if price <= lower and rsi < 35:
                pct = calculate_position_size(ctx, i)
                ctx.buy(percent=pct, reason='range_bb_lower')
        else:
            # 上轨卖出
            if price >= upper:
                ctx.sell_all(reason='range_bb_upper')
            # 回到中轨部分止盈
            elif price >= middle and rsi > 60:
                ctx.sell(percent=0.4, reason='range_middle_tp')


# ============================================
# 策略 7: 趋势跟踪 (Trend Following)
# ============================================

def trend_following_factory(params: Dict[str, Any]) -> Callable:
    def strategy(ctx: StrategyContext):
        trend_following_strategy(ctx, params)
    return strategy


def trend_following_setup_factory(params: Dict[str, Any]) -> Callable:
    def setup(ctx: StrategyContext):
        trend_following_setup(ctx, params)
    return setup


def trend_following_setup(ctx: StrategyContext, params: Dict[str, Any] = None):
    """趋势跟踪 — 指标初始化"""
    params = params or {}
    c = ctx.close
    h = ctx.high
    lo = ctx.low
    v = ctx.volume

    fast = params.get('ema_fast', 20)
    slow = params.get('ema_slow', 50)

    ctx.indicators['trend_ema_fast'] = EMA(c, fast)
    ctx.indicators['trend_ema_slow'] = EMA(c, slow)
    ctx.indicators['trend_sma_200'] = SMA(c, 200)

    # ATR 用于追踪止损和仓位管理
    ctx.indicators['trend_atr'] = ATR(h, lo, c, 14)

    # 动量: RSI
    ctx.indicators['trend_rsi'] = RSI(c, 14)

    # 突破: N周期最高/最低
    ctx.indicators['highest_20'] = HIGHEST(h, 20)
    ctx.indicators['lowest_20'] = LOWEST(lo, 20)

    # 市场状态
    regime_indicators = setup_regime_indicators(h, lo, c, v)
    for k, arr in regime_indicators.items():
        ctx.indicators[f'regime_{k}'] = arr


def trend_following_strategy(ctx: StrategyContext, params: Dict[str, Any] = None):
    """
    趋势跟踪策略
    
    逻辑:
    1. 确认趋势: EMA20 > EMA50 > SMA200 (多头排列)
    2. 入场: 价格突破20周期高点 + RSI 回调区间
    3. 出场: EMA金叉变死叉 或 ATR追踪止损
    4. 仓位: 基于ATR的动态仓位
    """
    i = ctx.bar_index
    if i < 205:
        return

    price = ctx.current_price
    ema_fast = ctx.indicators['trend_ema_fast'][i]
    ema_slow = ctx.indicators['trend_ema_slow'][i]
    sma_200 = ctx.indicators['trend_sma_200'][i]
    rsi = ctx.indicators['trend_rsi'][i]
    atr = ctx.indicators['trend_atr'][i]
    highest_20 = ctx.indicators['highest_20'][i]

    if any(np.isnan(x) for x in [ema_fast, ema_slow, sma_200, rsi, atr]):
        return

    # 连续亏损保护 (宽松)
    if check_consecutive_losses(ctx, max_losses=5):
        return  # 暂停开新仓

    # 多头排列: 快线 > 慢线 (放宽条件，不要求>200SMA)
    is_bullish = ema_fast > ema_slow
    is_strong_bullish = ema_fast > ema_slow > sma_200
    
    # 价格在均线上方
    price_above_ema = price > ema_slow

    if not ctx.position.is_open:
        if is_bullish and rsi > 35 and rsi < 70:
            # 强势多头排列: 更大仓位
            if is_strong_bullish and (price >= highest_20 or price > ema_fast):
                pct = calculate_position_size(ctx, i)
                ctx.buy(percent=pct, reason='trend_strong_breakout')
            # 弱势多头: 回调到EMA附近
            elif price_above_ema and price <= ema_fast * 1.01 and rsi < 50:
                pct = calculate_position_size(ctx, i) * 0.6
                ctx.buy(percent=pct, reason='trend_pullback')
    else:
        # 追踪止损: 基于ATR
        trailing_stop_price = ctx.position.highest_price - 3.0 * atr
        
        # 趋势反转出场 (用更宽松条件)
        if ema_fast < ema_slow and rsi < 40:
            ctx.sell_all(reason='trend_reversal')
        elif price < trailing_stop_price:
            ctx.sell_all(reason='atr_trailing_stop')
        elif rsi > 80:
            ctx.sell(percent=0.3, reason='rsi_overbought')


# ============================================
# 策略 8: 多策略组合 (Combo Strategy)
# ============================================

def combo_strategy_factory(params: Dict[str, Any]) -> Callable:
    def strategy(ctx: StrategyContext):
        combo_strategy(ctx, params)
    return strategy


def combo_strategy_setup_factory(params: Dict[str, Any]) -> Callable:
    def setup(ctx: StrategyContext):
        combo_strategy_setup(ctx, params)
    return setup


def combo_strategy_setup(ctx: StrategyContext, params: Dict[str, Any] = None):
    """
    组合策略 — 指标初始化 (合并两个子策略的指标)
    """
    adaptive_bollinger_setup(ctx, params)
    trend_following_setup(ctx, params)


def combo_strategy(ctx: StrategyContext, params: Dict[str, Any] = None):
    """
    多策略组合引擎 v2 — 统一信号管理
    
    核心改进: 不直接调用子策略函数（避免冲突），
    而是提取两个策略的信号，综合判断后统一执行。
    
    信号来源:
      A) 趋势信号: EMA排列 + 突破 + RSI
      B) 均值回归信号: 布林带 + RSI
      
    组合规则:
      - 两个信号一致 → 加大仓位
      - 只有一个信号 → 标准仓位
      - 信号矛盾 → 用市场状态决定
    """
    i = ctx.bar_index
    if i < 205:
        return

    price = ctx.current_price

    # ====== 收集信号 ======
    # 趋势信号
    ema_fast = ctx.indicators.get('trend_ema_fast', ctx.indicators.get('ema_12'))
    ema_slow = ctx.indicators.get('trend_ema_slow', ctx.indicators.get('ema_26'))
    sma_200 = ctx.indicators.get('trend_sma_200', ctx.indicators.get('sma_200'))
    
    ema_f = ema_fast[i] if ema_fast is not None and not np.isnan(ema_fast[i]) else None
    ema_s = ema_slow[i] if ema_slow is not None and not np.isnan(ema_slow[i]) else None
    sma200 = sma_200[i] if sma_200 is not None and not np.isnan(sma_200[i]) else None
    
    trend_bullish = (ema_f is not None and ema_s is not None and ema_f > ema_s)
    trend_strong = (trend_bullish and sma200 is not None and ema_s > sma200)

    # 均值回归信号 (布林带)
    bb_lower = ctx.indicators.get('bb_range_lower')
    bb_upper = ctx.indicators.get('bb_range_upper')
    bb_middle = ctx.indicators.get('bb_range_middle')
    
    bb_l = bb_lower[i] if bb_lower is not None and not np.isnan(bb_lower[i]) else None
    bb_u = bb_upper[i] if bb_upper is not None and not np.isnan(bb_upper[i]) else None
    bb_m = bb_middle[i] if bb_middle is not None and not np.isnan(bb_middle[i]) else None

    at_bb_lower = (bb_l is not None and price <= bb_l)
    at_bb_upper = (bb_u is not None and price >= bb_u)
    above_bb_mid = (bb_m is not None and price >= bb_m)

    # RSI
    rsi_val = ctx.indicators.get('rsi_14')
    rsi = rsi_val[i] if rsi_val is not None and not np.isnan(rsi_val[i]) else 50

    # ATR
    atr_val = ctx.indicators.get('atr_14')
    atr = atr_val[i] if atr_val is not None and not np.isnan(atr_val[i]) else 0

    # 连续亏损保护
    if check_consecutive_losses(ctx, max_losses=5):
        return

    # ====== 开仓逻辑 ======
    if not ctx.position.is_open:
        buy_signal = False
        reason = ''
        size_mult = 1.0

        # 信号1: 强势趋势 + 回调 (高确信)
        if trend_strong and rsi < 45 and price > ema_s:
            buy_signal = True
            reason = 'combo_trend_strong'
            size_mult = 1.0

        # 信号2: 趋势多头 + 布林带下轨 (高确信)
        elif trend_bullish and at_bb_lower and rsi < 40:
            buy_signal = True
            reason = 'combo_trend_bb_lower'
            size_mult = 1.0

        # 信号3: 仅布林带下轨 + RSI超卖 (中确信)
        elif at_bb_lower and rsi < 30:
            buy_signal = True
            reason = 'combo_bb_oversold'
            size_mult = 0.6

        # 信号4: 趋势回调到EMA (中确信)
        elif trend_bullish and rsi < 40 and ema_f is not None and price <= ema_f * 1.01:
            buy_signal = True
            reason = 'combo_trend_pullback'
            size_mult = 0.7

        if buy_signal:
            pct = calculate_position_size(ctx, i) * size_mult
            ctx.buy(percent=pct, reason=reason)

    # ====== 平仓逻辑 ======
    else:
        sell_signal = False
        sell_pct = 1.0  # 1.0 = 全平
        reason = ''

        # 卖出信号1: 趋势反转 + RSI弱 (全平)
        if not trend_bullish and rsi < 40:
            sell_signal = True
            reason = 'combo_trend_reversal'

        # 卖出信号2: 布林带上轨 (部分止盈)
        elif at_bb_upper and rsi > 70:
            sell_signal = True
            sell_pct = 0.5
            reason = 'combo_bb_upper_tp'

        # 卖出信号3: RSI极端超买 (部分止盈)
        elif rsi > 80:
            sell_signal = True
            sell_pct = 0.3
            reason = 'combo_rsi_extreme'

        # 卖出信号4: ATR追踪止损
        elif atr > 0:
            trailing_stop = ctx.position.highest_price - 3.0 * atr
            if price < trailing_stop:
                sell_signal = True
                reason = 'combo_atr_trailing'

        if sell_signal:
            if sell_pct >= 0.95:
                ctx.sell_all(reason=reason)
            else:
                ctx.sell(percent=sell_pct, reason=reason)


# ============================================
# 工厂函数映射 (供优化器使用)
# ============================================

STRATEGY_REGISTRY = {
    'adaptive_bollinger': {
        'factory': adaptive_bollinger_factory,
        'setup_factory': adaptive_bollinger_setup_factory,
        'description': '自适应布林带策略 - 根据市场状态动态调参',
    },
    'trend_following': {
        'factory': trend_following_factory,
        'setup_factory': trend_following_setup_factory,
        'description': '趋势跟踪策略 - 多头排列+突破入场',
    },
    'combo': {
        'factory': combo_strategy_factory,
        'setup_factory': combo_strategy_setup_factory,
        'description': '多策略组合 - 根据市场状态切换策略',
    },
}
