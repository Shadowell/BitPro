"""
策略注册表 — 将数据库策略ID映射到v2回测引擎的策略函数
=====================================================

v2引擎需要两个函数:
  - strategy_fn(ctx: StrategyContext): 每根K线调用的策略逻辑
  - setup_fn(ctx: StrategyContext): 初始化自定义指标 (可选)

本模块同时提供:
  - 每个策略的默认回测配置 (推荐周期、止损等)
  - 自动识别策略类型 (通过名称关键字)
"""
import numpy as np
import logging
from typing import Callable, Optional, Dict, Any, Tuple

from app.services.strategy_backtest import StrategyContext, BacktestConfig

logger = logging.getLogger(__name__)


# ============================================
# 基础策略 (Phase 1-2, 纯v2函数式)
# ============================================

def buy_and_hold_strategy(ctx: StrategyContext, params: Dict[str, Any] = None):
    """Buy & Hold 基准策略"""
    if ctx.bar_index == 0 and not ctx.position.is_open:
        ctx.buy(percent=0.95, reason='buy_and_hold')

def buy_and_hold_setup(ctx: StrategyContext):
    pass


def dual_ma_strategy(ctx: StrategyContext, params: Dict[str, Any] = None):
    """双均线金叉死叉策略"""
    i = ctx.bar_index
    sma_fast = ctx.indicators.get('sma_7')
    sma_slow = ctx.indicators.get('sma_25')
    if sma_fast is None or sma_slow is None:
        return
    if np.isnan(sma_fast[i]) or np.isnan(sma_slow[i]):
        return

    if not ctx.position.is_open:
        # 金叉买入
        if i > 0 and sma_fast[i-1] <= sma_slow[i-1] and sma_fast[i] > sma_slow[i]:
            ctx.buy(percent=0.90, reason='golden_cross')
    else:
        # 死叉卖出
        if i > 0 and sma_fast[i-1] >= sma_slow[i-1] and sma_fast[i] < sma_slow[i]:
            ctx.sell_all(reason='death_cross')

def dual_ma_setup(ctx: StrategyContext):
    pass  # 默认指标已有 sma_7, sma_25


def rsi_oversold_strategy(ctx: StrategyContext, params: Dict[str, Any] = None):
    """RSI超卖反弹策略"""
    i = ctx.bar_index
    rsi = ctx.indicators.get('rsi_14')
    if rsi is None or np.isnan(rsi[i]):
        return

    if not ctx.position.is_open:
        if rsi[i] < 30:
            ctx.buy(percent=0.90, reason='rsi_oversold')
    else:
        if rsi[i] > 70:
            ctx.sell_all(reason='rsi_overbought')

def rsi_oversold_setup(ctx: StrategyContext):
    pass


def bollinger_reversion_strategy(ctx: StrategyContext, params: Dict[str, Any] = None):
    """布林带均值回归策略"""
    i = ctx.bar_index
    bb_upper = ctx.indicators.get('bb_upper')
    bb_lower = ctx.indicators.get('bb_lower')
    close = ctx.close[i]
    if bb_upper is None or np.isnan(bb_upper[i]) or np.isnan(bb_lower[i]):
        return

    if not ctx.position.is_open:
        if close <= bb_lower[i]:
            ctx.buy(percent=0.90, reason='bb_lower_touch')
    else:
        if close >= bb_upper[i]:
            ctx.sell_all(reason='bb_upper_touch')

def bollinger_reversion_setup(ctx: StrategyContext):
    pass


def macd_rsi_strategy(ctx: StrategyContext, params: Dict[str, Any] = None):
    """MACD+RSI 多因子组合策略"""
    i = ctx.bar_index
    macd_hist = ctx.indicators.get('macd_hist')
    rsi = ctx.indicators.get('rsi_14')
    if macd_hist is None or rsi is None:
        return
    if np.isnan(macd_hist[i]) or np.isnan(rsi[i]):
        return

    if not ctx.position.is_open:
        # MACD柱由负转正 + RSI < 60
        if i > 0 and macd_hist[i-1] < 0 and macd_hist[i] > 0 and rsi[i] < 60:
            ctx.buy(percent=0.90, reason='macd_cross_up_rsi_ok')
    else:
        # MACD柱由正转负 或 RSI > 75
        if (i > 0 and macd_hist[i-1] > 0 and macd_hist[i] < 0) or rsi[i] > 75:
            ctx.sell_all(reason='macd_cross_down_or_rsi_high')

def macd_rsi_setup(ctx: StrategyContext):
    pass


# ============================================
# Phase 3 策略 — 从 pro_strategies.py 导入
# ============================================

from app.services.pro_strategies import (
    adaptive_bollinger_strategy, adaptive_bollinger_setup,
    trend_following_strategy, trend_following_setup,
    combo_strategy, combo_strategy_setup,
)


# ============================================
# 自动交易策略 — v2回测版本
# (对应 auto_strategies.py 中的 ProStrategyBase 类)
# ============================================

def smart_trend_strategy(ctx: StrategyContext, params: Dict[str, Any] = None):
    """智能趋势跟踪策略 — EMA排列+MACD+RSI多重确认"""
    i = ctx.bar_index
    ema9 = ctx.indicators.get('ema_9')
    ema21 = ctx.indicators.get('ema_21')
    ema55 = ctx.indicators.get('ema_55')
    macd_hist = ctx.indicators.get('macd_hist')
    rsi = ctx.indicators.get('rsi_14')
    if ema9 is None or ema55 is None or macd_hist is None or rsi is None:
        return
    if np.isnan(ema55[i]) or np.isnan(macd_hist[i]) or np.isnan(rsi[i]):
        return

    if not ctx.position.is_open:
        # EMA多头排列 + MACD>0 + RSI<70
        if ema9[i] > ema21[i] > ema55[i] and macd_hist[i] > 0 and rsi[i] < 70:
            ctx.buy(percent=0.90, reason='ema_bullish_macd_rsi')
    else:
        # EMA空头排列 或 MACD转负 或 RSI>75
        if (ema9[i] < ema21[i] < ema55[i]) or (i > 0 and macd_hist[i-1] > 0 and macd_hist[i] < 0) or rsi[i] > 75:
            ctx.sell_all(reason='ema_bearish_or_macd_cross_down')

def smart_trend_setup(ctx: StrategyContext):
    from app.services.strategy_backtest import EMA
    c = ctx.close
    ctx.indicators['ema_9'] = EMA(c, 9)
    ctx.indicators['ema_21'] = EMA(c, 21)
    ctx.indicators['ema_55'] = EMA(c, 55)


def mean_reversion_strategy(ctx: StrategyContext, params: Dict[str, Any] = None):
    """均值回归策略 — 布林带+RSI极值反转"""
    i = ctx.bar_index
    bb_upper = ctx.indicators.get('bb_upper')
    bb_lower = ctx.indicators.get('bb_lower')
    bb_middle = ctx.indicators.get('bb_middle')
    rsi = ctx.indicators.get('rsi_14')
    close = ctx.close[i]
    if bb_upper is None or rsi is None or np.isnan(bb_upper[i]) or np.isnan(rsi[i]):
        return

    # BB%B 指标
    bb_width = bb_upper[i] - bb_lower[i]
    if bb_width <= 0:
        return
    bb_pct_b = (close - bb_lower[i]) / bb_width

    if not ctx.position.is_open:
        # 超卖: BB%B < 0.05 且 RSI < 30
        if bb_pct_b < 0.05 and rsi[i] < 30:
            ctx.buy(percent=0.90, reason='bb_oversold_rsi_low')
    else:
        # 到中轨止盈 或 超买反转
        if close >= bb_middle[i] or (bb_pct_b > 0.95 and rsi[i] > 70):
            ctx.sell_all(reason='bb_mean_revert_or_overbought')

def mean_reversion_setup(ctx: StrategyContext):
    pass  # 用默认的 bb_upper/bb_lower/bb_middle + rsi_14


def momentum_breakout_strategy(ctx: StrategyContext, params: Dict[str, Any] = None):
    """动量突破策略 — 唐奇安通道+成交量确认"""
    i = ctx.bar_index
    period = 20
    if i < period:
        return
    don_high = ctx.indicators.get('don_high')
    don_low = ctx.indicators.get('don_low')
    if don_high is None or np.isnan(don_high[i]):
        return

    close = ctx.close[i]
    vol = ctx.volume[i]
    vol_ma = ctx.indicators.get('vol_ma_20')
    vol_confirm = vol_ma is not None and not np.isnan(vol_ma[i]) and vol > vol_ma[i] * 1.5

    if not ctx.position.is_open:
        # 价格突破上通道 + 放量
        if close > don_high[i] and vol_confirm:
            ctx.buy(percent=0.90, reason='breakout_high_volume')
    else:
        # 跌破下通道
        if close < don_low[i]:
            ctx.sell_all(reason='break_below_channel')

def momentum_breakout_setup(ctx: StrategyContext):
    """计算唐奇安通道和成交量均线"""
    h = ctx.high
    lo = ctx.low
    v = ctx.volume
    n = len(h)
    period = 20

    don_high = np.full(n, np.nan)
    don_low = np.full(n, np.nan)
    vol_ma = np.full(n, np.nan)

    for j in range(period, n):
        don_high[j] = np.max(h[j-period:j])  # 前20根最高价(不含当前)
        don_low[j] = np.min(lo[j-period:j])
        vol_ma[j] = np.mean(v[j-period:j])

    ctx.indicators['don_high'] = don_high
    ctx.indicators['don_low'] = don_low
    ctx.indicators['vol_ma_20'] = vol_ma


def scalping_strategy(ctx: StrategyContext, params: Dict[str, Any] = None):
    """高频剥头皮策略 — RSI(7)极值+布林带(10)偏离"""
    i = ctx.bar_index
    rsi7 = ctx.indicators.get('rsi_7')
    bb_upper_10 = ctx.indicators.get('bb_upper_10')
    bb_lower_10 = ctx.indicators.get('bb_lower_10')
    if rsi7 is None or bb_upper_10 is None or np.isnan(rsi7[i]) or np.isnan(bb_upper_10[i]):
        return

    close = ctx.close[i]

    if not ctx.position.is_open:
        # RSI(7) < 20 且 价格低于下轨
        if rsi7[i] < 20 and close < bb_lower_10[i]:
            ctx.buy(percent=0.90, reason='scalp_oversold')
    else:
        # RSI(7) > 80 或 价格高于上轨
        if rsi7[i] > 80 or close > bb_upper_10[i]:
            ctx.sell_all(reason='scalp_overbought')

def scalping_setup(ctx: StrategyContext):
    """计算短周期布林带(10,2)"""
    from app.services.strategy_backtest import BBANDS
    c = ctx.close
    bb_up, bb_mid, bb_lo = BBANDS(c, 10, 2.0)
    ctx.indicators['bb_upper_10'] = bb_up
    ctx.indicators['bb_middle_10'] = bb_mid
    ctx.indicators['bb_lower_10'] = bb_lo


# ============================================
# 策略注册表
# ============================================

# 每个条目: (strategy_fn, setup_fn, default_stop_loss, recommended_timeframe)
STRATEGY_FUNCTION_MAP: Dict[str, Dict[str, Any]] = {
    # Phase 1-2 基础策略
    'buy_and_hold': {
        'fn': buy_and_hold_strategy,
        'setup': buy_and_hold_setup,
        'stop_loss': None,
        'timeframe': '1d',
    },
    'dual_ma': {
        'fn': dual_ma_strategy,
        'setup': dual_ma_setup,
        'stop_loss': 0.05,
        'timeframe': '1d',
    },
    'rsi_oversold': {
        'fn': rsi_oversold_strategy,
        'setup': rsi_oversold_setup,
        'stop_loss': 0.05,
        'timeframe': '1d',
    },
    'bollinger_reversion': {
        'fn': bollinger_reversion_strategy,
        'setup': bollinger_reversion_setup,
        'stop_loss': 0.05,
        'timeframe': '1d',
    },
    'macd_rsi': {
        'fn': macd_rsi_strategy,
        'setup': macd_rsi_setup,
        'stop_loss': 0.05,
        'timeframe': '1d',
    },
    # Phase 3 高级策略 (内部有ATR追踪止损, 不需要外部硬止损)
    'adaptive_bollinger': {
        'fn': adaptive_bollinger_strategy,
        'setup': adaptive_bollinger_setup,
        'stop_loss': None,  # 策略内部ATR追踪止损
        'timeframe': '4h',
    },
    'trend_following': {
        'fn': trend_following_strategy,
        'setup': trend_following_setup,
        'stop_loss': None,  # 策略内部有止损逻辑
        'timeframe': '4h',
    },
    'combo': {
        'fn': combo_strategy,
        'setup': combo_strategy_setup,
        'stop_loss': None,  # 组合策略内部管理
        'timeframe': '4h',
    },
    # 自动交易策略 (v2回测版)
    'smart_trend': {
        'fn': smart_trend_strategy,
        'setup': smart_trend_setup,
        'stop_loss': 0.08,  # 8% 适合4h周期BTC波动
        'timeframe': '4h',
    },
    'mean_reversion': {
        'fn': mean_reversion_strategy,
        'setup': mean_reversion_setup,
        'stop_loss': 0.05,
        'timeframe': '1h',
    },
    'momentum_breakout': {
        'fn': momentum_breakout_strategy,
        'setup': momentum_breakout_setup,
        'stop_loss': 0.08,  # 8% 适合4h周期
        'timeframe': '4h',
    },
    'scalping': {
        'fn': scalping_strategy,
        'setup': scalping_setup,
        'stop_loss': 0.015,
        'timeframe': '15m',
    },
    # 多时间框架 (回测时用趋势跟踪逻辑)
    'multi_timeframe': {
        'fn': trend_following_strategy,
        'setup': trend_following_setup,
        'stop_loss': None,
        'timeframe': '4h',
    },
    # 资金费率 (回测时用均值回归逻辑做近似)
    'funding_rate_pro': {
        'fn': mean_reversion_strategy,
        'setup': mean_reversion_setup,
        'stop_loss': 0.03,
        'timeframe': '1h',
    },
    # 实盘版别名 — 映射到同一回测函数
    'adaptive_bollinger_live': {
        'fn': adaptive_bollinger_strategy,
        'setup': adaptive_bollinger_setup,
        'stop_loss': None,
        'timeframe': '4h',
    },
    'trend_following_live': {
        'fn': trend_following_strategy,
        'setup': trend_following_setup,
        'stop_loss': None,
        'timeframe': '4h',
    },
}


# ============================================
# 策略解析 — 从数据库策略到 v2 回测函数
# ============================================

def resolve_strategy_by_key(strategy_key: str) -> Optional[Dict[str, Any]]:
    """根据 strategy_key 直接解析到 v2 策略函数"""
    return STRATEGY_FUNCTION_MAP.get(strategy_key)


def resolve_strategy(strategy_name: str, config: Dict = None) -> Optional[Dict[str, Any]]:
    """
    根据策略名称/config解析到v2策略函数
    优先使用 config 中的 strategy_key，其次按名称关键字匹配

    Returns:
        {'fn': callable, 'setup': callable, 'stop_loss': float, 'timeframe': str}
        or None if not found
    """
    # 优先: 使用 config 中的 strategy_key (精确匹配)
    if config and config.get('strategy_key'):
        key = config['strategy_key']
        if key in STRATEGY_FUNCTION_MAP:
            return STRATEGY_FUNCTION_MAP[key]

    # 兜底: 按名称关键字匹配
    _KEYWORD_MAP = [
        ('智能趋势', 'smart_trend'),
        ('均值回归策略(自动交易版)', 'mean_reversion'),
        ('动量突破', 'momentum_breakout'),
        ('剥头皮', 'scalping'),
        ('多时间框架', 'multi_timeframe'),
        ('资金费率', 'funding_rate_pro'),
        ('自适应布林带(实盘', 'adaptive_bollinger'),
        ('趋势跟踪(实盘', 'trend_following'),
        ('自适应布林带', 'adaptive_bollinger'),
        ('Buy & Hold', 'buy_and_hold'),
        ('双均线', 'dual_ma'),
        ('RSI超卖', 'rsi_oversold'),
        ('布林带均值回归', 'bollinger_reversion'),
        ('MACD+RSI', 'macd_rsi'),
        ('趋势跟踪', 'trend_following'),
        ('多策略组合', 'combo'),
    ]
    for keyword, key in _KEYWORD_MAP:
        if keyword in strategy_name:
            return STRATEGY_FUNCTION_MAP.get(key)

    # 最终兜底: 直接用名称当 key
    name_lower = strategy_name.lower()
    if name_lower in STRATEGY_FUNCTION_MAP:
        return STRATEGY_FUNCTION_MAP[name_lower]

    return None


def get_strategy_for_id(strategy_id: int) -> Optional[Dict[str, Any]]:
    """
    根据数据库策略ID获取v2策略函数

    Returns:
        {'fn': callable, 'setup': callable, 'stop_loss': float, 'timeframe': str, 'name': str}
    """
    from app.db.local_db import db_instance as db
    strategy = db.get_strategy_by_id(strategy_id)
    if not strategy:
        return None

    name = strategy.get('name', '')
    config = strategy.get('config') or {}
    resolved = resolve_strategy(name, config)

    if resolved:
        return {**resolved, 'name': name}

    logger.warning(f"策略 #{strategy_id} '{name}' 无法映射到v2函数")
    return None


def list_available_strategies() -> Dict[str, str]:
    """列出所有可用的v2策略"""
    return {k: v['fn'].__doc__ or k for k, v in STRATEGY_FUNCTION_MAP.items()}
