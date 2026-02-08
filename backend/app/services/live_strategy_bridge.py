"""
实盘策略桥接器 (Live Strategy Bridge)
======================================
Phase 5 核心组件

将 Phase 3 的高级策略（自适应布林带、趋势跟踪）
桥接到 AutoTrader 的 ProStrategyBase 接口，使其能在实盘中运行。

核心挑战:
  - Phase3策略使用 StrategyContext (v2回测框架)
  - AutoTrader使用 ProStrategyBase.execute(klines, equity)
  - 本模块做转换和桥接

使用:
    from app.services.live_strategy_bridge import AdaptiveBollingerLive

    strategy = AdaptiveBollingerLive({'symbol': 'BTC/USDT:USDT'})
    strategy.initialize(10000)
    result = strategy.execute(klines, current_equity)
    # result = {'action': 'buy', 'amount': 0.01, 'price': 97000, ...}
"""
import time
import logging
import numpy as np
from typing import Dict, List, Any, Optional

from app.services.auto_strategies import ProStrategyBase
from app.services.risk_manager import RiskManager, RiskConfig
from app.services.indicators import (
    SMA, EMA, RSI, BBANDS, ATR, MACD, CROSS_ABOVE, CROSS_BELOW,
    HIGHEST, LOWEST, VOLATILITY,
)
from app.services.market_regime import (
    detect_regime, setup_regime_indicators, MarketRegime,
    ADX as calc_ADX, bollinger_bandwidth, sma_slope,
)

logger = logging.getLogger(__name__)


def _klines_to_np(klines: List[Dict]) -> Dict[str, np.ndarray]:
    """K线列表转numpy数组"""
    open_arr = np.array([k['open'] for k in klines], dtype=float)
    high_arr = np.array([k['high'] for k in klines], dtype=float)
    low_arr = np.array([k['low'] for k in klines], dtype=float)
    close_arr = np.array([k['close'] for k in klines], dtype=float)
    volume_arr = np.array([k.get('volume', 0) for k in klines], dtype=float)
    return {
        'open': open_arr,
        'high': high_arr,
        'low': low_arr,
        'close': close_arr,
        'volume': volume_arr,
    }


class AdaptiveBollingerLive(ProStrategyBase):
    """
    自适应布林带策略 — 实盘版
    ============================
    Phase 3 最优策略，桥接到 AutoTrader 框架

    逻辑:
    1. 检测市场状态 (趋势/震荡/高波动)
    2. 根据状态动态调整布林带参数和入场条件
    3. ATR动态仓位管理
    4. 多层风控

    信号产生流程:
    klines → numpy → 指标 → 市场状态 → 信号决策 → 仓位计算
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="自适应布林带 (Live)", config=config)
        # 策略参数
        self.bb_period = config.get('bb_period', 20) if config else 20
        self.bb_std = config.get('bb_std', 2.0) if config else 2.0
        self.rsi_period = config.get('rsi_period', 14) if config else 14
        self.ema_fast = config.get('ema_fast', 12) if config else 12
        self.ema_slow = config.get('ema_slow', 26) if config else 26
        self.atr_period = config.get('atr_period', 14) if config else 14

        # 状态
        self._position_side = None   # 'long' / None
        self._entry_price = 0.0
        self._position_size = 0.0
        self._highest_since_entry = 0.0
        self._consecutive_losses = 0
        self._last_regime = MarketRegime.UNKNOWN

    def generate_signal(self, klines: List[Dict], **kwargs) -> Dict:
        """
        生成交易信号

        Returns:
            {
                'action': 'buy'/'sell'/'close'/'hold',
                'confidence': 0-1,
                'reason': str,
                'amount': float (仓位数量),
                'price': float,
                'stop_loss': float,
                'take_profit': float,
                'signal': {'regime': str, 'rsi': float, ...},
            }
        """
        if not klines or len(klines) < 50:
            return {'action': 'hold', 'reason': '数据不足'}

        # ---- 转换数据 ----
        arrays = _klines_to_np(klines)
        close = arrays['close']
        high = arrays['high']
        low = arrays['low']
        i = len(close) - 1  # 最新bar
        price = close[i]

        # ---- 计算指标 ----
        bb_upper, bb_mid, bb_lower = BBANDS(close, self.bb_period, self.bb_std)
        rsi = RSI(close, self.rsi_period)
        ema_f = EMA(close, self.ema_fast)
        ema_s = EMA(close, self.ema_slow)
        atr = ATR(high, low, close, self.atr_period)
        macd_line, signal_line, macd_hist = MACD(close)

        rsi_val = rsi[i] if not np.isnan(rsi[i]) else 50
        atr_val = atr[i] if not np.isnan(atr[i]) else 0
        atr_pct = atr_val / price if price > 0 else 0

        # ---- 市场状态检测 ----
        regime_indicators = setup_regime_indicators(high, low, close)
        regime = detect_regime(
            high, low, close, i,
            adx_arr=regime_indicators.get('adx'),
            plus_di_arr=regime_indicators.get('plus_di'),
            minus_di_arr=regime_indicators.get('minus_di'),
            vol_percentile_arr=regime_indicators.get('vol_percentile'),
            sma_slope_arr=regime_indicators.get('sma_slope'),
        )
        self._last_regime = regime

        # ---- 信号元数据 ----
        signal_meta = {
            'regime': regime.value,
            'rsi': round(rsi_val, 1),
            'atr_pct': round(atr_pct * 100, 2),
            'price': round(price, 2),
            'bb_upper': round(bb_upper[i], 2) if not np.isnan(bb_upper[i]) else 0,
            'bb_lower': round(bb_lower[i], 2) if not np.isnan(bb_lower[i]) else 0,
            'ema_fast': round(ema_f[i], 2) if not np.isnan(ema_f[i]) else 0,
            'ema_slow': round(ema_s[i], 2) if not np.isnan(ema_s[i]) else 0,
        }

        # ---- 连续亏损保护 ----
        if self._consecutive_losses >= 5:
            self.log(f"连续亏损{self._consecutive_losses}次，暂停入场", "warning")
            return {
                'action': 'hold', 'reason': f'连续亏损{self._consecutive_losses}次暂停',
                'signal': signal_meta,
            }

        # ---- 波动率熔断 ----
        if atr_pct > 0.08:
            self.log(f"波动率过高 ATR/P={atr_pct:.1%}，暂停", "warning")
            return {
                'action': 'hold', 'reason': f'波动率熔断 {atr_pct:.1%}',
                'signal': signal_meta,
            }

        # ====== 持仓管理 ======
        if self._position_side == 'long':
            return self._manage_long_position(
                price, close, high, low, i,
                bb_upper, bb_mid, bb_lower, rsi_val, ema_f, ema_s,
                atr_val, atr_pct, regime, signal_meta
            )

        # ====== 入场信号 ======
        return self._generate_entry_signal(
            price, close, high, low, i,
            bb_upper, bb_mid, bb_lower, rsi_val, ema_f, ema_s,
            atr_val, atr_pct, regime, signal_meta
        )

    def _generate_entry_signal(
        self, price, close, high, low, i,
        bb_upper, bb_mid, bb_lower, rsi_val, ema_f, ema_s,
        atr_val, atr_pct, regime, signal_meta,
    ) -> Dict:
        """生成入场信号"""
        action = 'hold'
        reason = ''
        confidence = 0
        position_pct = 0  # 仓位比例 0~1

        if regime == MarketRegime.TRENDING_UP:
            # 趋势多头: 回撤到布林中轨买入
            if price <= bb_mid[i] and rsi_val < 50 and ema_f[i] > ema_s[i]:
                action = 'buy'
                reason = 'trend_up_pullback_to_mid'
                confidence = 0.7
                position_pct = 0.8
            elif price <= bb_lower[i] and rsi_val < 35:
                action = 'buy'
                reason = 'trend_up_oversold'
                confidence = 0.8
                position_pct = 0.9

        elif regime == MarketRegime.TRENDING_DOWN:
            # 趋势空头: 只在极度超卖时小仓位
            if rsi_val < 25 and price <= bb_lower[i]:
                action = 'buy'
                reason = 'trend_down_extreme_oversold'
                confidence = 0.4
                position_pct = 0.3

        elif regime == MarketRegime.RANGING:
            # 震荡: 布林下轨超卖买入
            if price <= bb_lower[i] and rsi_val < 35:
                action = 'buy'
                reason = 'ranging_bb_lower_oversold'
                confidence = 0.6
                position_pct = 0.7

        elif regime == MarketRegime.HIGH_VOLATILITY:
            # 高波动: 极度超卖才入场, 小仓位
            if rsi_val < 20 and price <= bb_lower[i]:
                action = 'buy'
                reason = 'high_vol_extreme_oversold'
                confidence = 0.3
                position_pct = 0.3

        if action == 'hold':
            return {'action': 'hold', 'reason': f'无入场信号 ({regime.value})', 'signal': signal_meta}

        # ---- 计算仓位和价格 ----
        # ATR动态仓位: 波动越大仓位越小
        risk_per_trade = 0.03
        stop_distance = atr_val * 2
        if stop_distance > 0 and price > 0:
            risk_based_pct = risk_per_trade / (stop_distance / price)
            position_pct = min(position_pct, risk_based_pct)
        position_pct = max(0.10, min(position_pct, 0.90))

        stop_loss = price - atr_val * 2
        take_profit = price + atr_val * 3

        self.log(f"入场信号: {reason} | {regime.value} | RSI={rsi_val:.0f} | 仓位{position_pct:.0%}")

        return {
            'action': 'buy',
            'confidence': confidence,
            'reason': reason,
            'position_pct': position_pct,
            'price': price,
            'stop_loss': round(stop_loss, 2),
            'take_profit': round(take_profit, 2),
            'signal': signal_meta,
        }

    def _manage_long_position(
        self, price, close, high, low, i,
        bb_upper, bb_mid, bb_lower, rsi_val, ema_f, ema_s,
        atr_val, atr_pct, regime, signal_meta,
    ) -> Dict:
        """管理多头持仓"""
        self._highest_since_entry = max(self._highest_since_entry, price)

        # ---- 1. ATR追踪止损 ----
        trail_stop = self._highest_since_entry - atr_val * 2.5
        if price < trail_stop:
            pnl = (price - self._entry_price) / self._entry_price
            self._close_live_position(pnl)
            return {
                'action': 'close',
                'reason': f'ATR追踪止损 (trail={trail_stop:.0f})',
                'price': price,
                'pnl': round(pnl * self._position_size * self._entry_price, 2),
                'signal': signal_meta,
            }

        # ---- 2. 硬止损 ----
        hard_stop = self._entry_price * 0.95
        if price < hard_stop:
            pnl = (price - self._entry_price) / self._entry_price
            self._close_live_position(pnl)
            return {
                'action': 'close',
                'reason': f'硬止损 5%',
                'price': price,
                'pnl': round(pnl * self._position_size * self._entry_price, 2),
                'signal': signal_meta,
            }

        # ---- 3. 布林上轨止盈 ----
        if price >= bb_upper[i] and rsi_val > 70:
            pnl = (price - self._entry_price) / self._entry_price
            self._close_live_position(pnl)
            return {
                'action': 'close',
                'reason': f'布林上轨止盈 RSI={rsi_val:.0f}',
                'price': price,
                'pnl': round(pnl * self._position_size * self._entry_price, 2),
                'signal': signal_meta,
            }

        # ---- 4. 趋势转空离场 ----
        if regime == MarketRegime.TRENDING_DOWN and rsi_val < 40:
            pnl = (price - self._entry_price) / self._entry_price
            self._close_live_position(pnl)
            return {
                'action': 'close',
                'reason': f'趋势转空',
                'price': price,
                'pnl': round(pnl * self._position_size * self._entry_price, 2),
                'signal': signal_meta,
            }

        return {'action': 'hold', 'reason': '持仓中', 'signal': signal_meta}

    def _close_live_position(self, pnl_pct: float):
        """关闭持仓并更新状态"""
        if pnl_pct > 0:
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1

        self._position_side = None
        self._entry_price = 0
        self._position_size = 0
        self._highest_since_entry = 0

    def execute(self, klines: List[Dict], current_equity: float,
                exchange_api=None, **kwargs) -> Dict:
        """执行策略 (重写父类方法)"""
        if not self.is_initialized:
            self.initialize(current_equity)

        signal = self.generate_signal(klines, **kwargs)
        action = signal.get('action', 'hold')
        current_price = klines[-1]['close'] if klines else 0

        # 如果是买入信号，计算具体仓位
        if action == 'buy' and self._position_side is None:
            position_pct = signal.get('position_pct', 0.5)
            trade_capital = current_equity * position_pct
            amount = trade_capital / current_price if current_price > 0 else 0

            # 记录开仓
            self._position_side = 'long'
            self._entry_price = current_price
            self._position_size = amount
            self._highest_since_entry = current_price

            signal['amount'] = round(amount, 6)

            # 检查风控
            positions = self.risk_manager.get_positions()
            risk_check = self.risk_manager.check_entry(
                self.config.get('symbol', 'BTC/USDT'),
                'long', current_price, amount, current_equity
            )
            if not risk_check.get('allowed', True):
                self._position_side = None
                self._entry_price = 0
                self._position_size = 0
                signal['action'] = 'hold'
                signal['reason'] = f"风控拦截: {risk_check.get('reason', '')}"
                self.log(f"风控拦截: {risk_check.get('reason', '')}", "warning")

        return signal


class TrendFollowingLive(ProStrategyBase):
    """
    趋势跟踪策略 — 实盘版
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="趋势跟踪 (Live)", config=config)
        self.ema_fast = config.get('ema_fast', 12) if config else 12
        self.ema_slow = config.get('ema_slow', 26) if config else 26
        self.atr_period = config.get('atr_period', 14) if config else 14

        self._position_side = None
        self._entry_price = 0.0
        self._position_size = 0.0
        self._highest_since_entry = 0.0
        self._consecutive_losses = 0

    def generate_signal(self, klines: List[Dict], **kwargs) -> Dict:
        if not klines or len(klines) < 50:
            return {'action': 'hold', 'reason': '数据不足'}

        arrays = _klines_to_np(klines)
        close = arrays['close']
        high = arrays['high']
        low = arrays['low']
        i = len(close) - 1
        price = close[i]

        ema_f = EMA(close, self.ema_fast)
        ema_s = EMA(close, self.ema_slow)
        atr = ATR(high, low, close, self.atr_period)
        rsi = RSI(close, 14)

        rsi_val = rsi[i] if not np.isnan(rsi[i]) else 50
        atr_val = atr[i] if not np.isnan(atr[i]) else 0

        trend_bullish = ema_f[i] > ema_s[i]
        recent_high = np.max(high[max(0, i-20):i+1])

        signal_meta = {
            'rsi': round(rsi_val, 1),
            'ema_fast': round(ema_f[i], 2),
            'ema_slow': round(ema_s[i], 2),
            'trend': 'bullish' if trend_bullish else 'bearish',
        }

        # 持仓管理
        if self._position_side == 'long':
            self._highest_since_entry = max(self._highest_since_entry, price)
            trail_stop = self._highest_since_entry - atr_val * 3
            hard_stop = self._entry_price * 0.95

            if price < trail_stop or price < hard_stop:
                pnl = (price - self._entry_price) / self._entry_price
                if pnl > 0:
                    self._consecutive_losses = 0
                else:
                    self._consecutive_losses += 1
                self._position_side = None
                self._entry_price = 0
                self._position_size = 0
                return {
                    'action': 'close',
                    'reason': 'trailing_stop' if price < trail_stop else 'hard_stop',
                    'price': price,
                    'pnl': round(pnl * 100, 2),
                    'signal': signal_meta,
                }

            if not trend_bullish and rsi_val < 40:
                pnl = (price - self._entry_price) / self._entry_price
                if pnl > 0:
                    self._consecutive_losses = 0
                else:
                    self._consecutive_losses += 1
                self._position_side = None
                self._entry_price = 0
                self._position_size = 0
                return {
                    'action': 'close',
                    'reason': 'trend_reversal',
                    'price': price,
                    'pnl': round(pnl * 100, 2),
                    'signal': signal_meta,
                }

            return {'action': 'hold', 'reason': '持仓中', 'signal': signal_meta}

        # 入场
        if self._consecutive_losses >= 5:
            return {'action': 'hold', 'reason': f'连续亏损{self._consecutive_losses}次', 'signal': signal_meta}

        if trend_bullish and rsi_val < 60:
            # 突破或回撤入场
            if price >= recent_high * 0.99 or (price <= ema_f[i] * 1.01 and price > ema_s[i]):
                position_pct = 0.6
                stop_loss = price - atr_val * 3
                take_profit = price + atr_val * 5

                amount = 0
                self._position_side = 'long'
                self._entry_price = price
                self._highest_since_entry = price

                self.log(f"趋势入场: RSI={rsi_val:.0f} EMA_F > EMA_S")

                return {
                    'action': 'buy',
                    'confidence': 0.6,
                    'reason': 'trend_entry',
                    'position_pct': position_pct,
                    'price': price,
                    'stop_loss': round(stop_loss, 2),
                    'take_profit': round(take_profit, 2),
                    'signal': signal_meta,
                }

        return {'action': 'hold', 'reason': '无信号', 'signal': signal_meta}

    def execute(self, klines: List[Dict], current_equity: float,
                exchange_api=None, **kwargs) -> Dict:
        if not self.is_initialized:
            self.initialize(current_equity)

        signal = self.generate_signal(klines, **kwargs)
        action = signal.get('action', 'hold')
        current_price = klines[-1]['close'] if klines else 0

        if action == 'buy' and self._position_side == 'long':
            position_pct = signal.get('position_pct', 0.5)
            trade_capital = current_equity * position_pct
            amount = trade_capital / current_price if current_price > 0 else 0
            self._position_size = amount
            signal['amount'] = round(amount, 6)

        return signal
