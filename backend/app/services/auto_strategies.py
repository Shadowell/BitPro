"""
自动交易策略库 (Auto Strategies)
================================================
包含多种经过验证的专业级交易策略，每个策略都集成了：
- 信号系统 (numpy 指标库)
- 风控模块 (RiskManager)
- 自适应参数调整

策略列表:
1. SmartTrendStrategy     - 智能趋势跟踪（多指标确认）
2. MeanReversionStrategy  - 均值回归（布林带 + RSI）
3. MomentumBreakout       - 动量突破（唐奇安通道 + 成交量确认）
4. MultiTimeframeStrategy - 多时间框架（大小周期共振）
5. FundingRatePro         - 资金费率增强版（动态阈值 + 风控）
6. ScalpingStrategy       - 高频剥头皮（RSI 极值 + VWAP）
"""
import time
import math
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

from app.services.indicators import (
    SMA, EMA, MACD, RSI, KDJ, BBANDS, ATR, VOLATILITY,
    OBV, VWAP, CROSS_ABOVE, CROSS_BELOW, HIGHEST, LOWEST,
    klines_to_arrays,
)
from app.services.risk_manager import (
    RiskManager, RiskConfig, RiskCheckResult,
    StopType, PositionInfo
)

logger = logging.getLogger(__name__)


def _v(arr, i=-1):
    """安全取 numpy 值，NaN 返回 None"""
    val = arr[i]
    return None if np.isnan(val) else float(val)


# ============================================
# 策略基类
# ============================================

class ProStrategyBase:
    """专业策略基类 - 所有 Pro 策略继承此类"""
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}
        self.risk_manager = RiskManager(
            RiskConfig.from_dict(self.config.get('risk', {})) if 'risk' in self.config else RiskConfig()
        )
        self.is_initialized = False
        self.last_signal = "neutral"
        self.last_signal_time = 0
        self._logs: List[str] = []
    
    def log(self, message: str, level: str = "info"):
        timestamp = time.strftime("%H:%M:%S")
        log_entry = f"[{timestamp}][{self.name}] {message}"
        self._logs.append(log_entry)
        if len(self._logs) > 500:
            self._logs = self._logs[-250:]
        getattr(logger, level, logger.info)(log_entry)
    
    def get_logs(self, limit: int = 50) -> List[str]:
        return self._logs[-limit:]
    
    def initialize(self, initial_equity: float):
        self.risk_manager.initialize(initial_equity)
        self.is_initialized = True
        self.log(f"策略初始化: 初始资金={initial_equity:.2f} USDT")
    
    def generate_signal(self, klines: List[Dict], **kwargs) -> Dict:
        raise NotImplementedError
    
    def execute(self, klines: List[Dict], current_equity: float,
                exchange_api=None, **kwargs) -> Dict:
        if not self.is_initialized:
            self.initialize(current_equity)
        
        signal = self.generate_signal(klines, **kwargs)
        action = signal.get('action', 'hold')
        confidence = signal.get('confidence', 0)
        current_price = klines[-1]['close'] if klines else 0
        
        # 检查现有持仓
        positions = self.risk_manager.get_positions()
        for symbol, pos in positions.items():
            atr_val = self._get_current_atr(klines)
            should_exit, exit_reason = self.risk_manager.update_position(
                symbol, current_price, atr=atr_val
            )
            if should_exit:
                self.log(f"平仓信号: {exit_reason}")
                pnl = self.risk_manager.close_position(symbol, current_price, exit_reason)
                return {
                    'action': 'close', 'symbol': symbol,
                    'price': current_price, 'pnl': pnl, 'reason': exit_reason
                }
        
        if action == 'hold' or confidence < 0.3:
            return {'action': 'hold', 'signal': signal}
        
        symbol = self.config.get('symbol', 'BTC/USDT')
        atr_val = self._get_current_atr(klines)
        volatility = self._get_current_volatility(klines)
        
        sizing = self.risk_manager.calculate_position_size(
            symbol, 'long' if action == 'buy' else 'short',
            current_price, current_equity, atr=atr_val, volatility=volatility
        )
        amount = sizing['amount']
        
        risk_check = self.risk_manager.check_order(
            symbol, 'long' if action == 'buy' else 'short',
            amount, current_price, current_equity, atr=atr_val, volatility=volatility
        )
        
        if not risk_check.approved:
            self.log(f"风控拒绝: {'; '.join(risk_check.reasons)}", "warning")
            return {'action': 'blocked', 'reasons': risk_check.reasons}
        
        final_amount = risk_check.adjusted_amount or amount
        stop_loss = risk_check.stop_loss
        take_profit = risk_check.take_profit
        
        side = 'long' if action == 'buy' else 'short'
        self.risk_manager.open_position(
            symbol, side, final_amount, current_price,
            stop_loss=stop_loss, take_profit=take_profit
        )
        
        self.log(f"{'买入' if action == 'buy' else '卖出'} {final_amount:.6f} {symbol} @ {current_price:.2f} "
                f"SL={stop_loss:.2f} TP={take_profit:.2f} 信心={confidence:.0%}")
        
        return {
            'action': action, 'symbol': symbol, 'side': side,
            'amount': final_amount, 'price': current_price,
            'stop_loss': stop_loss, 'take_profit': take_profit,
            'confidence': confidence, 'signal': signal,
            'risk_check': {'warnings': risk_check.warnings, 'risk_level': risk_check.risk_level.value}
        }
    
    def _get_current_atr(self, klines: List[Dict], period: int = 14) -> float:
        if len(klines) < period + 1:
            return 0
        arr = klines_to_arrays(klines)
        atr_values = ATR(arr['high'], arr['low'], arr['close'], period)
        val = atr_values[-1]
        return 0.0 if np.isnan(val) else float(val)
    
    def _get_current_volatility(self, klines: List[Dict], period: int = 20) -> float:
        if len(klines) < period + 1:
            return 0
        arr = klines_to_arrays(klines)
        vol = VOLATILITY(arr['close'], period)
        val = vol[-1]
        return 0.0 if np.isnan(val) else float(val)


# ============================================
# 策略 1: 智能趋势跟踪
# ============================================

class SmartTrendStrategy(ProStrategyBase):
    """EMA多头/空头排列 + MACD确认 + RSI过滤"""
    
    def __init__(self, config: Dict = None):
        super().__init__("SmartTrend", config)
        self.ema_fast = self.config.get('ema_fast', 9)
        self.ema_mid = self.config.get('ema_mid', 21)
        self.ema_slow = self.config.get('ema_slow', 55)
        self.rsi_overbought = self.config.get('rsi_overbought', 70)
        self.rsi_oversold = self.config.get('rsi_oversold', 30)
    
    def generate_signal(self, klines: List[Dict], **kwargs) -> Dict:
        if len(klines) < 60:
            return {'action': 'hold', 'confidence': 0, 'reason': '数据不足'}
        
        arr = klines_to_arrays(klines)
        close = arr['close']
        n = len(close)
        idx = n - 1
        prev = idx - 1
        
        ema_f = EMA(close, self.ema_fast)
        ema_m = EMA(close, self.ema_mid)
        ema_s = EMA(close, self.ema_slow)
        _, _, histogram = MACD(close)
        rsi_arr = RSI(close, 14)
        
        ef, em, es = _v(ema_f, idx), _v(ema_m, idx), _v(ema_s, idx)
        if any(v is None for v in [ef, em, es]):
            return {'action': 'hold', 'confidence': 0, 'reason': '指标计算中'}
        
        bullish_trend = ef > em > es
        bearish_trend = ef < em < es
        
        hist_cur = _v(histogram, idx)
        hist_prev = _v(histogram, prev)
        macd_bullish = hist_cur is not None and hist_cur > 0
        macd_bearish = hist_cur is not None and hist_cur < 0
        macd_cross_up = hist_cur is not None and hist_prev is not None and hist_cur > 0 and hist_prev <= 0
        macd_cross_down = hist_cur is not None and hist_prev is not None and hist_cur < 0 and hist_prev >= 0
        
        rsi_val = _v(rsi_arr, idx) or 50.0
        
        if bullish_trend and macd_bullish and rsi_val < self.rsi_overbought:
            confidence = 0.3
            reasons = ["EMA多头排列"]
            if macd_cross_up:
                confidence += 0.2; reasons.append("MACD金叉")
            if rsi_val < 45:
                confidence += 0.1; reasons.append(f"RSI={rsi_val:.0f}")
            ef_prev = _v(ema_f, prev)
            if ef_prev and ef > ef_prev:
                confidence += 0.15; reasons.append("均线加速")
            return {'action': 'buy', 'confidence': min(confidence, 1.0), 'reason': ' | '.join(reasons)}
        
        if bearish_trend and macd_bearish and rsi_val > self.rsi_oversold:
            confidence = 0.3
            reasons = ["EMA空头排列"]
            if macd_cross_down:
                confidence += 0.2; reasons.append("MACD死叉")
            if rsi_val > 55:
                confidence += 0.1; reasons.append(f"RSI={rsi_val:.0f}")
            return {'action': 'sell', 'confidence': min(confidence, 1.0), 'reason': ' | '.join(reasons)}
        
        return {'action': 'hold', 'confidence': 0, 'reason': '无明确信号'}


# ============================================
# 策略 2: 均值回归
# ============================================

class MeanReversionStrategy(ProStrategyBase):
    """布林带超买超卖 + RSI极值"""
    
    def __init__(self, config: Dict = None):
        super().__init__("MeanReversion", config)
        self.bb_period = self.config.get('bb_period', 20)
        self.bb_std = self.config.get('bb_std', 2.0)
        self.rsi_buy = self.config.get('rsi_buy', 30)
        self.rsi_sell = self.config.get('rsi_sell', 70)
    
    def generate_signal(self, klines: List[Dict], **kwargs) -> Dict:
        if len(klines) < 30:
            return {'action': 'hold', 'confidence': 0, 'reason': '数据不足'}
        
        arr = klines_to_arrays(klines)
        close = arr['close']
        idx = len(close) - 1
        price = float(close[idx])
        
        bb_u, bb_m, bb_l = BBANDS(close, self.bb_period, self.bb_std)
        rsi_arr = RSI(close, 14)
        
        bb_uv, bb_lv, bb_mv = _v(bb_u, idx), _v(bb_l, idx), _v(bb_m, idx)
        rsi_val = _v(rsi_arr, idx)
        
        if bb_uv is None or bb_lv is None or rsi_val is None or (bb_uv - bb_lv) == 0:
            return {'action': 'hold', 'confidence': 0, 'reason': '指标计算中'}
        
        pb = (price - bb_lv) / (bb_uv - bb_lv)
        
        if pb < 0.05 and rsi_val < self.rsi_buy:
            confidence = 0.4
            reasons = [f"BB%B={pb:.2f}", f"RSI={rsi_val:.0f}超卖"]
            if pb < 0: confidence += 0.2; reasons.append("破下轨")
            if rsi_val < 20: confidence += 0.15; reasons.append("极度超卖")
            if len(close) > 3 and close[-1] > close[-2] and close[-2] < close[-3]:
                confidence += 0.1; reasons.append("V型反转")
            return {'action': 'buy', 'confidence': min(confidence, 1.0), 'reason': ' | '.join(reasons),
                    'take_profit_target': bb_mv}
        
        if pb > 0.95 and rsi_val > self.rsi_sell:
            confidence = 0.4
            reasons = [f"BB%B={pb:.2f}", f"RSI={rsi_val:.0f}超买"]
            if pb > 1: confidence += 0.2; reasons.append("破上轨")
            if rsi_val > 80: confidence += 0.15; reasons.append("极度超买")
            return {'action': 'sell', 'confidence': min(confidence, 1.0), 'reason': ' | '.join(reasons),
                    'take_profit_target': bb_mv}
        
        return {'action': 'hold', 'confidence': 0, 'reason': '未达极值'}


# ============================================
# 策略 3: 动量突破
# ============================================

class MomentumBreakoutStrategy(ProStrategyBase):
    """唐奇安通道突破 + 成交量确认"""
    
    def __init__(self, config: Dict = None):
        super().__init__("MomentumBreakout", config)
        self.entry_period = self.config.get('entry_period', 20)
        self.volume_multiplier = self.config.get('volume_mult', 1.5)
    
    def generate_signal(self, klines: List[Dict], **kwargs) -> Dict:
        if len(klines) < self.entry_period + 5:
            return {'action': 'hold', 'confidence': 0, 'reason': '数据不足'}
        
        arr = klines_to_arrays(klines)
        close, high, low, volume = arr['close'], arr['high'], arr['low'], arr['volume']
        n = len(close)
        idx = n - 1
        prev = idx - 1
        price = float(close[idx])
        
        entry_high = HIGHEST(high, self.entry_period)
        entry_low = LOWEST(low, self.entry_period)
        eu = _v(entry_high, prev)
        el = _v(entry_low, prev)
        
        if eu is None or el is None:
            return {'action': 'hold', 'confidence': 0, 'reason': '指标计算中'}
        
        avg_vol = float(np.mean(volume[-20:])) if n >= 20 else float(np.mean(volume))
        cur_vol = float(volume[-1])
        vol_ok = avg_vol > 0 and cur_vol > avg_vol * self.volume_multiplier
        ch_width = (eu - el) / el if el > 0 else 0
        
        if price > eu:
            c = 0.4
            r = [f"突破{self.entry_period}日高点"]
            if vol_ok: c += 0.25; r.append("放量确认")
            if ch_width < 0.05: c += 0.15; r.append("窄幅突破")
            return {'action': 'buy', 'confidence': min(c, 1.0), 'reason': ' | '.join(r)}
        
        if price < el:
            c = 0.4
            r = [f"跌破{self.entry_period}日低点"]
            if vol_ok: c += 0.25; r.append("放量确认")
            if ch_width < 0.05: c += 0.15; r.append("窄幅跌破")
            return {'action': 'sell', 'confidence': min(c, 1.0), 'reason': ' | '.join(r)}
        
        return {'action': 'hold', 'confidence': 0, 'reason': '价格在通道内'}


# ============================================
# 策略 4: 多时间框架
# ============================================

class MultiTimeframeStrategy(ProStrategyBase):
    """大周期趋势 + 小周期精准入场"""
    
    def __init__(self, config: Dict = None):
        super().__init__("MultiTimeframe", config)
    
    def generate_signal(self, klines: List[Dict],
                       klines_higher: List[Dict] = None, **kwargs) -> Dict:
        if not klines_higher or len(klines_higher) < 60 or len(klines) < 30:
            return {'action': 'hold', 'confidence': 0, 'reason': '数据不足'}
        
        h = klines_to_arrays(klines_higher)
        h_ema_f = EMA(h['close'], 9)
        h_ema_s = EMA(h['close'], 21)
        h_idx = len(h['close']) - 1
        hef, hes = _v(h_ema_f, h_idx), _v(h_ema_s, h_idx)
        if hef is None or hes is None:
            return {'action': 'hold', 'confidence': 0, 'reason': '大周期指标不足'}
        
        higher_bullish = hef > hes
        higher_bearish = hef < hes
        
        s = klines_to_arrays(klines)
        s_rsi = RSI(s['close'], 14)
        _, _, s_hist = MACD(s['close'])
        s_bb_u, _, s_bb_l = BBANDS(s['close'])
        s_k, _, _ = KDJ(s['high'], s['low'], s['close'])
        si = len(s['close']) - 1
        
        s_rsi_val = _v(s_rsi, si) or 50
        s_h = _v(s_hist, si)
        s_hp = _v(s_hist, si - 1) if si > 0 else None
        
        s_buv, s_blv = _v(s_bb_u, si), _v(s_bb_l, si)
        sp = float(s['close'][si])
        s_pb = (sp - s_blv) / (s_buv - s_blv) if s_buv and s_blv and (s_buv - s_blv) > 0 else None
        s_kv = _v(s_k, si)
        
        if higher_bullish:
            c = 0.2; r = ["大周期看多"]
            if s_rsi_val < 40: c += 0.2; r.append(f"小RSI={s_rsi_val:.0f}回调")
            if s_pb is not None and s_pb < 0.2: c += 0.15; r.append("触布林下轨")
            if s_kv is not None and s_kv < 20: c += 0.15; r.append(f"KDJ={s_kv:.0f}超卖")
            if s_h and s_hp and s_h > 0 and s_hp <= 0: c += 0.15; r.append("MACD金叉")
            if c >= 0.4:
                return {'action': 'buy', 'confidence': min(c, 1.0), 'reason': ' | '.join(r)}
        
        if higher_bearish:
            c = 0.2; r = ["大周期看空"]
            if s_rsi_val > 60: c += 0.2; r.append(f"小RSI={s_rsi_val:.0f}反弹")
            if s_pb is not None and s_pb > 0.8: c += 0.15; r.append("触布林上轨")
            if s_kv is not None and s_kv > 80: c += 0.15; r.append(f"KDJ={s_kv:.0f}超买")
            if s_h and s_hp and s_h < 0 and s_hp >= 0: c += 0.15; r.append("MACD死叉")
            if c >= 0.4:
                return {'action': 'sell', 'confidence': min(c, 1.0), 'reason': ' | '.join(r)}
        
        return {'action': 'hold', 'confidence': 0, 'reason': '大小周期未共振'}


# ============================================
# 策略 5: 资金费率增强版
# ============================================

class FundingRateProStrategy(ProStrategyBase):
    """动态费率阈值 + 技术面过滤"""
    
    def __init__(self, config: Dict = None):
        super().__init__("FundingRatePro", config)
        self.min_rate = self.config.get('min_rate', 0.0001)
        self.high_rate = self.config.get('high_rate', 0.0005)
        self.max_negative_rate = self.config.get('max_neg', -0.0002)
        self.rate_history: List[float] = []
    
    def generate_signal(self, klines: List[Dict],
                       funding_rate: float = None, predicted_rate: float = None, **kwargs) -> Dict:
        if funding_rate is None:
            return {'action': 'hold', 'confidence': 0, 'reason': '无资金费率数据'}
        
        self.rate_history.append(funding_rate)
        if len(self.rate_history) > 100:
            self.rate_history = self.rate_history[-100:]
        
        dynamic_min = self.min_rate
        if len(self.rate_history) >= 10:
            avg = sum(self.rate_history[-10:]) / 10
            dynamic_min = max(avg * 0.5, self.min_rate)
        
        rsi_val = 50.0
        if len(klines) >= 30:
            arr = klines_to_arrays(klines)
            rsi_arr = RSI(arr['close'], 14)
            rsi_val = _v(rsi_arr) or 50
        
        has_pos = len(self.risk_manager.get_positions()) > 0
        
        if funding_rate > dynamic_min and not has_pos:
            c = 0.3; r = [f"费率={funding_rate:.4%}"]
            if funding_rate > self.high_rate: c += 0.3; r.append("高费率")
            if predicted_rate and predicted_rate > dynamic_min: c += 0.15; r.append(f"预测={predicted_rate:.4%}")
            if rsi_val > 60: c += 0.1; r.append(f"RSI={rsi_val:.0f}")
            return {'action': 'sell', 'confidence': min(c, 1.0), 'reason': ' | '.join(r)}
        
        if has_pos and funding_rate < self.max_negative_rate:
            return {'action': 'buy', 'confidence': 0.8, 'reason': f'费率转负={funding_rate:.4%}', 'is_close': True}
        
        return {'action': 'hold', 'confidence': 0, 'reason': f'费率={funding_rate:.4%}未达阈值'}


# ============================================
# 策略 6: 高频剥头皮
# ============================================

class ScalpingStrategy(ProStrategyBase):
    """RSI极值 + VWAP偏离 + 快进快出"""
    
    def __init__(self, config: Dict = None):
        default_risk = {
            'default_stop_loss_pct': 0.015,
            'default_take_profit_pct': 0.02,
            'risk_per_trade_pct': 0.01,
            'max_trades_per_hour': 20,
            'cooldown_after_loss': 30,
        }
        if config and 'risk' not in config: config['risk'] = default_risk
        elif not config: config = {'risk': default_risk}
        super().__init__("Scalping", config)
        self.rsi_low = self.config.get('rsi_low', 20)
        self.rsi_high = self.config.get('rsi_high', 80)
        self.vwap_dev = self.config.get('vwap_dev', 0.01)
    
    def generate_signal(self, klines: List[Dict], **kwargs) -> Dict:
        if len(klines) < 20:
            return {'action': 'hold', 'confidence': 0, 'reason': '数据不足'}
        
        arr = klines_to_arrays(klines)
        close, high, low, volume = arr['close'], arr['high'], arr['low'], arr['volume']
        idx = len(close) - 1
        price = float(close[idx])
        
        rsi_arr = RSI(close, 7)
        vwap_arr = VWAP(high, low, close, volume)
        bb_u, _, bb_l = BBANDS(close, 10, 2.0)
        
        rsi_val = _v(rsi_arr, idx)
        vwap_val = _v(vwap_arr, idx)
        if rsi_val is None or vwap_val is None:
            return {'action': 'hold', 'confidence': 0, 'reason': '指标不足'}
        
        vd = (price - vwap_val) / vwap_val if vwap_val > 0 else 0
        bu, bl = _v(bb_u, idx), _v(bb_l, idx)
        pb = (price - bl) / (bu - bl) if bu and bl and (bu - bl) > 0 else None
        
        if rsi_val < self.rsi_low and vd < -self.vwap_dev:
            c = 0.4; r = [f"RSI7={rsi_val:.0f}超卖", f"VWAP偏离{vd:.2%}"]
            if pb is not None and pb < 0: c += 0.2; r.append("破布林下轨")
            if klines[-1]['close'] > klines[-1]['open']: c += 0.15; r.append("反弹阳线")
            return {'action': 'buy', 'confidence': min(c, 0.85), 'reason': ' | '.join(r)}
        
        if rsi_val > self.rsi_high and vd > self.vwap_dev:
            c = 0.4; r = [f"RSI7={rsi_val:.0f}超买", f"VWAP偏离+{vd:.2%}"]
            if pb is not None and pb > 1: c += 0.2; r.append("破布林上轨")
            if klines[-1]['close'] < klines[-1]['open']: c += 0.15; r.append("回落阴线")
            return {'action': 'sell', 'confidence': min(c, 0.85), 'reason': ' | '.join(r)}
        
        return {'action': 'hold', 'confidence': 0, 'reason': '未达极值'}


# ============================================
# 策略注册表
# ============================================

# Phase 5: 导入实盘策略桥接
from app.services.live_strategy_bridge import AdaptiveBollingerLive, TrendFollowingLive

STRATEGY_REGISTRY: Dict[str, type] = {
    'smart_trend': SmartTrendStrategy,
    'mean_reversion': MeanReversionStrategy,
    'momentum_breakout': MomentumBreakoutStrategy,
    'multi_timeframe': MultiTimeframeStrategy,
    'funding_rate_pro': FundingRateProStrategy,
    'scalping': ScalpingStrategy,
    # Phase 5: 实盘策略 (Phase3最优策略桥接)
    'adaptive_bollinger_live': AdaptiveBollingerLive,
    'trend_following_live': TrendFollowingLive,
}

STRATEGY_INFO = {
    'smart_trend':        {'name': '智能趋势跟踪', 'description': 'EMA排列+MACD+RSI', 'risk_level': '中', 'timeframe': '1h/4h', 'suitable_for': '趋势行情'},
    'mean_reversion':     {'name': '均值回归', 'description': '布林带+RSI极值', 'risk_level': '中低', 'timeframe': '15m/1h', 'suitable_for': '震荡行情'},
    'momentum_breakout':  {'name': '动量突破', 'description': '唐奇安通道+成交量确认', 'risk_level': '中高', 'timeframe': '4h/1d', 'suitable_for': '突破行情'},
    'multi_timeframe':    {'name': '多时间框架', 'description': '大周期趋势+小周期入场', 'risk_level': '中', 'timeframe': '15m+4h', 'suitable_for': '趋势行情(高胜率)'},
    'funding_rate_pro':   {'name': '资金费率增强版', 'description': '动态费率阈值+技术面过滤', 'risk_level': '低', 'timeframe': '不限', 'suitable_for': '永续合约套利'},
    'scalping':           {'name': '高频剥头皮', 'description': 'RSI极值+VWAP偏离', 'risk_level': '中', 'timeframe': '1m/5m/15m', 'suitable_for': '高流动性交易对'},
    # Phase 5: 实盘策略
    'adaptive_bollinger_live': {'name': '自适应布林带(实盘)', 'description': 'Phase3最优策略: 市场状态自适应+动态仓位+多层风控, Walk-Forward 75%一致性', 'risk_level': '中', 'timeframe': '4h', 'suitable_for': 'BTC/ETH趋势+震荡行情', 'recommended': True},
    'trend_following_live':    {'name': '趋势跟踪(实盘)', 'description': 'EMA多头排列+突破入场+ATR追踪止损, 365天+16%收益', 'risk_level': '中', 'timeframe': '4h', 'suitable_for': '强趋势行情'},
}


def create_strategy(strategy_type: str, config: Dict = None) -> ProStrategyBase:
    """工厂函数：创建策略实例"""
    cls = STRATEGY_REGISTRY.get(strategy_type)
    if not cls:
        raise ValueError(f"Unknown strategy: {strategy_type}. Available: {list(STRATEGY_REGISTRY.keys())}")
    return cls(config)
