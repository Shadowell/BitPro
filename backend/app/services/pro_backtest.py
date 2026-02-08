"""
Pro 策略回测引擎
================================================
为 pro_strategies 量身打造的回测系统：
1. 逐 K 线回放，每根 K 线调用策略 generate_signal + execute
2. 模拟撮合、手续费、滑点
3. 完整绩效指标计算
4. 回测结果 & 权益曲线持久化到 SQLite
5. 支持批量回测全部策略
"""
import asyncio
import json
import time
import math
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import logging

from app.db.local_db import db_instance as db
from app.exchange import exchange_manager
from app.services.auto_strategies import (
    ProStrategyBase, create_strategy, STRATEGY_REGISTRY, STRATEGY_INFO
)
from app.services.risk_manager import RiskConfig

logger = logging.getLogger(__name__)


# ============================================================
# 数据库 DDL  —  新增两张表，init_db() 时自动建
# ============================================================

_PRO_BACKTEST_DDL = """
CREATE TABLE IF NOT EXISTS pro_backtest_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_type TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    exchange      TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    timeframe     TEXT NOT NULL,
    start_date    TEXT NOT NULL,
    end_date      TEXT NOT NULL,

    -- 资金
    initial_capital REAL NOT NULL,
    final_capital   REAL,

    -- 绩效
    total_return     REAL,
    annual_return    REAL,
    max_drawdown     REAL,
    sharpe_ratio     REAL,
    sortino_ratio    REAL,
    calmar_ratio     REAL,
    win_rate         REAL,
    profit_factor    REAL,
    total_trades     INTEGER,
    winning_trades   INTEGER,
    losing_trades    INTEGER,
    avg_win          REAL,
    avg_loss         REAL,
    largest_win      REAL,
    largest_loss     REAL,
    avg_holding_bars INTEGER,

    -- 交易明细 JSON
    trades_json TEXT,

    -- 策略参数 / 风控参数 JSON
    strategy_config TEXT,
    risk_config     TEXT,

    status     TEXT DEFAULT 'completed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pro_backtest_equity (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    backtest_id     INTEGER NOT NULL,
    bar_index       INTEGER NOT NULL,
    timestamp       INTEGER NOT NULL,
    equity          REAL NOT NULL,
    cash            REAL NOT NULL,
    position_value  REAL NOT NULL,
    drawdown_pct    REAL DEFAULT 0,
    FOREIGN KEY (backtest_id) REFERENCES pro_backtest_results(id)
);

CREATE INDEX IF NOT EXISTS idx_pbe_backtest
ON pro_backtest_equity(backtest_id, bar_index);
"""


def ensure_tables():
    """确保回测专用表存在"""
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.executescript(_PRO_BACKTEST_DDL)
    conn.commit()
    conn.close()


# ============================================================
# 回测交易记录
# ============================================================

@dataclass
class BTTrade:
    """回测中的一笔完整交易 (开→平)"""
    entry_time: int
    exit_time: int
    side: str           # long / short
    entry_price: float
    exit_price: float
    amount: float
    pnl: float
    pnl_pct: float
    fee: float
    bars_held: int
    exit_reason: str = ""


# ============================================================
# 回测配置
# ============================================================

@dataclass
class ProBacktestConfig:
    strategy_type: str
    exchange: str = "okx"
    symbol: str = "BTC/USDT"
    timeframe: str = "4h"
    start_date: str = "2024-06-01"
    end_date: str = "2026-02-07"
    initial_capital: float = 10000
    commission: float = 0.0004       # 0.04 %
    slippage: float = 0.0001         # 0.01 %
    strategy_config: Dict = field(default_factory=dict)
    risk_config: Dict = field(default_factory=dict)
    # 多时间框架策略需要高周期
    higher_timeframe: str = ""


# ============================================================
# 回测引擎核心
# ============================================================

class ProBacktestEngine:
    """Pro 策略回测引擎"""

    # ---- 公开 API ----

    async def run(self, cfg: ProBacktestConfig) -> Dict:
        """
        运行单个策略回测，返回结果 dict（同时写入数据库）
        """
        ensure_tables()

        strategy = create_strategy(cfg.strategy_type, cfg.strategy_config)
        strategy.initialize(cfg.initial_capital)

        # 获取 K 线数据
        klines = await self._load_klines(
            cfg.exchange, cfg.symbol, cfg.timeframe,
            cfg.start_date, cfg.end_date
        )
        if not klines or len(klines) < 60:
            return {"error": f"K线数据不足: {len(klines) if klines else 0} 条 (最少60)"}

        # 多时间框架策略: 加载大周期数据
        higher_klines = None
        if cfg.strategy_type == "multi_timeframe" and cfg.higher_timeframe:
            higher_klines = await self._load_klines(
                cfg.exchange, cfg.symbol, cfg.higher_timeframe,
                cfg.start_date, cfg.end_date
            )

        logger.info(f"[ProBacktest] {cfg.strategy_type} | {cfg.symbol} {cfg.timeframe} "
                     f"| {len(klines)} bars | {cfg.start_date}~{cfg.end_date}")

        # 执行回测
        equity_curve, trades = self._simulate(
            strategy, klines, cfg, higher_klines
        )

        # 计算绩效
        metrics = self._calc_metrics(equity_curve, trades, cfg)

        # 持久化
        backtest_id = self._save(cfg, metrics, equity_curve, trades)

        result = {
            "backtest_id": backtest_id,
            "strategy_type": cfg.strategy_type,
            "strategy_name": STRATEGY_INFO.get(cfg.strategy_type, {}).get("name", cfg.strategy_type),
            "symbol": cfg.symbol,
            "timeframe": cfg.timeframe,
            "period": f"{cfg.start_date} ~ {cfg.end_date}",
            "bars": len(klines),
            **metrics,
            "equity_curve_points": len(equity_curve),
            "trades_count": len(trades),
        }
        return result

    async def run_all(self, exchange: str = "okx", symbol: str = "BTC/USDT",
                      timeframe: str = "4h", start_date: str = "2024-06-01",
                      end_date: str = "2026-02-07",
                      initial_capital: float = 10000) -> List[Dict]:
        """
        批量回测所有策略（跳过 multi_timeframe 除非有高周期数据）
        """
        results = []
        for stype in STRATEGY_REGISTRY:
            cfg = ProBacktestConfig(
                strategy_type=stype,
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                higher_timeframe="1d" if stype == "multi_timeframe" else "",
            )
            try:
                r = await self.run(cfg)
                results.append(r)
                logger.info(f"[ProBacktest] {stype} done: return={r.get('total_return', '?')}%")
            except Exception as e:
                logger.error(f"[ProBacktest] {stype} failed: {e}")
                results.append({"strategy_type": stype, "error": str(e)})
        return results

    # ---- 私有: K 线加载 ----

    async def _load_klines(self, exchange: str, symbol: str, timeframe: str,
                           start_date: str, end_date: str) -> List[Dict]:
        """优先本地 DB，不够再走交易所 API"""
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

        local = db.get_klines(
            exchange=exchange, symbol=symbol, timeframe=timeframe,
            limit=999999, start=start_ts, end=end_ts,
        )
        if local and len(local) >= 60:
            logger.info(f"  本地加载 {len(local)} 条 {symbol} {timeframe}")
            return local

        # 交易所回退
        ex = exchange_manager.get_exchange(exchange)
        if not ex:
            return local or []

        tf_ms = {
            "1m": 60_000, "5m": 300_000, "15m": 900_000,
            "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
        }
        interval = tf_ms.get(timeframe, 3_600_000)
        all_k: List[Dict] = []
        cur = start_ts
        while cur < end_ts:
            try:
                batch = ex.fetch_ohlcv(symbol, timeframe, limit=1000, since=cur)
                if not batch:
                    break
                for k in batch:
                    if start_ts <= k["timestamp"] <= end_ts:
                        all_k.append(k)
                cur = batch[-1]["timestamp"] + interval
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.warning(f"  fetch_ohlcv 失败: {e}")
                break

        if all_k:
            db.insert_klines(exchange, symbol, timeframe, all_k)
        return all_k or local or []

    # ---- 私有: 核心模拟 ----

    def _simulate(self, strategy: ProStrategyBase, klines: List[Dict],
                  cfg: ProBacktestConfig,
                  higher_klines: List[Dict] = None
                  ) -> Tuple[List[Dict], List[BTTrade]]:
        """
        逐 K 线回放，调用策略 generate_signal，模拟开平仓
        """
        cash = cfg.initial_capital
        position = 0.0        # 正=多仓数量, 负=空仓数量
        entry_price = 0.0
        entry_bar = 0
        entry_side = ""

        equity_curve: List[Dict] = []
        completed_trades: List[BTTrade] = []

        lookback = 60  # 至少给策略 60 根K线

        for i in range(lookback, len(klines)):
            bar = klines[i]
            price = bar["close"]
            window = klines[max(0, i - 200):i + 1]   # 最多200根窗口

            # ---------- 生成信号 ----------
            try:
                extra = {}
                if higher_klines and cfg.strategy_type == "multi_timeframe":
                    # 找到当前 bar 时间之前的大周期 K 线
                    h_window = [k for k in higher_klines if k["timestamp"] <= bar["timestamp"]]
                    extra["klines_higher"] = h_window[-200:] if len(h_window) > 200 else h_window

                if cfg.strategy_type == "funding_rate_pro":
                    # 模拟资金费率
                    extra["funding_rate"] = 0.0001 + 0.0003 * math.sin(i * 0.05)

                signal = strategy.generate_signal(window, **extra)
            except Exception:
                signal = {"action": "hold"}

            action = signal.get("action", "hold")
            confidence = signal.get("confidence", 0)

            # ---------- 交易执行 ----------
            # 1) 有仓位时检查是否需要平仓
            if position != 0:
                should_close = False
                close_reason = ""

                # 策略主动反向信号 → 平仓
                if position > 0 and action == "sell" and confidence >= 0.3:
                    should_close = True
                    close_reason = "策略卖出信号"
                elif position < 0 and action == "buy" and confidence >= 0.3:
                    should_close = True
                    close_reason = "策略买入信号"

                # 简化止损止盈 (ATR 2倍止损, 3倍止盈)
                if not should_close and entry_price > 0:
                    move_pct = (price - entry_price) / entry_price
                    if position > 0:
                        if move_pct < -0.03:
                            should_close, close_reason = True, "止损-3%"
                        elif move_pct > 0.06:
                            should_close, close_reason = True, "止盈+6%"
                    else:
                        if move_pct > 0.03:
                            should_close, close_reason = True, "止损+3%"
                        elif move_pct < -0.06:
                            should_close, close_reason = True, "止盈-6%"

                if should_close:
                    abs_pos = abs(position)
                    exit_price = price * (1 - cfg.slippage) if position > 0 else price * (1 + cfg.slippage)
                    fee = abs_pos * exit_price * cfg.commission

                    if position > 0:
                        pnl = (exit_price - entry_price) * abs_pos - fee
                        cash += abs_pos * exit_price - fee
                    else:
                        pnl = (entry_price - exit_price) * abs_pos - fee
                        # 空仓平仓: 拿回保证金 + PnL
                        cash += abs_pos * entry_price + pnl

                    pnl_pct = pnl / (abs_pos * entry_price) * 100 if entry_price > 0 else 0

                    completed_trades.append(BTTrade(
                        entry_time=klines[entry_bar]["timestamp"],
                        exit_time=bar["timestamp"],
                        side=entry_side,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        amount=abs_pos,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        fee=fee,
                        bars_held=i - entry_bar,
                        exit_reason=close_reason,
                    ))

                    position = 0.0
                    entry_price = 0.0

            # 2) 无仓位时检查是否开仓
            if position == 0 and action in ("buy", "sell") and confidence >= 0.3:
                # 固定仓位: 每次用当前现金的 25%，但不超过现金的 90%
                alloc = cash * 0.25
                if alloc < 10:
                    continue  # 资金不足，跳过
                exec_price = price * (1 + cfg.slippage) if action == "buy" else price * (1 - cfg.slippage)
                amount = alloc / exec_price
                fee = amount * exec_price * cfg.commission

                if action == "buy":
                    cash -= (amount * exec_price + fee)
                    position = amount
                    entry_side = "long"
                else:
                    # 空仓: 冻结全额保证金
                    cash -= (amount * exec_price + fee)
                    position = -amount
                    entry_side = "short"

                entry_price = exec_price
                entry_bar = i

            # ---------- 记录权益 ----------
            if position > 0:
                pos_value = position * price
                equity = cash + pos_value
            elif position < 0:
                abs_p = abs(position)
                # 空仓权益 = 现金 + 冻结保证金 + 浮动盈亏
                unrealized_pnl = (entry_price - price) * abs_p
                pos_value = abs_p * entry_price  # 冻结保证金
                equity = cash + pos_value + unrealized_pnl
            else:
                pos_value = 0
                equity = cash

            equity_curve.append({
                "bar_index": i,
                "timestamp": bar["timestamp"],
                "equity": equity,
                "cash": cash,
                "position_value": pos_value,
            })

        # 最后强制平仓
        if position != 0:
            last_price = klines[-1]["close"]
            abs_pos = abs(position)
            fee = abs_pos * last_price * cfg.commission
            if position > 0:
                pnl = (last_price - entry_price) * abs_pos - fee
                cash += abs_pos * last_price - fee
            else:
                pnl = (entry_price - last_price) * abs_pos - fee
                cash += abs_pos * entry_price + pnl

            completed_trades.append(BTTrade(
                entry_time=klines[entry_bar]["timestamp"],
                exit_time=klines[-1]["timestamp"],
                side=entry_side,
                entry_price=entry_price,
                exit_price=last_price,
                amount=abs_pos,
                pnl=pnl,
                pnl_pct=pnl / (abs_pos * entry_price) * 100 if entry_price else 0,
                fee=fee,
                bars_held=len(klines) - 1 - entry_bar,
                exit_reason="回测结束强平",
            ))

            if equity_curve:
                equity_curve[-1]["equity"] = cash

        return equity_curve, completed_trades

    # ---- 私有: 绩效计算 ----

    def _calc_metrics(self, equity_curve: List[Dict], trades: List[BTTrade],
                      cfg: ProBacktestConfig) -> Dict:
        if not equity_curve:
            return {}

        equities = np.array([e["equity"] for e in equity_curve])
        initial = cfg.initial_capital
        final = float(equities[-1])

        total_return = (final - initial) / initial * 100

        # 时间跨度
        t0 = equity_curve[0]["timestamp"]
        t1 = equity_curve[-1]["timestamp"]
        days = max((t1 - t0) / 86_400_000, 1)

        annual_return = ((1 + total_return / 100) ** (365 / days) - 1) * 100

        # 回撤
        peak = np.maximum.accumulate(equities)
        dd = (peak - equities) / peak * 100
        max_dd = float(np.max(dd))

        # 注入回撤到曲线
        for i, ec in enumerate(equity_curve):
            ec["drawdown_pct"] = float(dd[i])

        # 收益率序列
        rets = np.diff(equities) / equities[:-1]
        avg_ret = float(np.mean(rets)) if len(rets) > 0 else 0
        std_ret = float(np.std(rets, ddof=1)) if len(rets) > 1 else 1

        # 周期因子 (4h → 6 bars/day → ~2190/year)
        tf_periods = {"1m": 525_600, "5m": 105_120, "15m": 35_040,
                      "1h": 8_760, "4h": 2_190, "1d": 365}
        ann_factor = tf_periods.get(cfg.timeframe, 2190)

        sharpe = (avg_ret * ann_factor) / (std_ret * math.sqrt(ann_factor)) if std_ret > 0 else 0
        neg_rets = rets[rets < 0]
        downside_std = float(np.std(neg_rets, ddof=1)) if len(neg_rets) > 1 else 1
        sortino = (avg_ret * ann_factor) / (downside_std * math.sqrt(ann_factor)) if downside_std > 0 else 0
        calmar = annual_return / max_dd if max_dd > 0 else 0

        # 交易统计
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        total_win = sum(t.pnl for t in wins)
        total_loss = abs(sum(t.pnl for t in losses))

        return {
            "initial_capital": initial,
            "final_capital": round(final, 2),
            "total_return": round(total_return, 2),
            "annual_return": round(annual_return, 2),
            "max_drawdown": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "calmar_ratio": round(calmar, 3),
            "total_trades": len(trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
            "profit_factor": round(total_win / total_loss, 2) if total_loss > 0 else 0,
            "avg_win": round(total_win / len(wins), 2) if wins else 0,
            "avg_loss": round(total_loss / len(losses), 2) if losses else 0,
            "largest_win": round(max((t.pnl for t in wins), default=0), 2),
            "largest_loss": round(min((t.pnl for t in losses), default=0), 2),
            "avg_holding_bars": round(sum(t.bars_held for t in trades) / len(trades)) if trades else 0,
            "total_fees": round(sum(t.fee for t in trades), 2),
        }

    # ---- 私有: 持久化 ----

    def _save(self, cfg: ProBacktestConfig, metrics: Dict,
              equity_curve: List[Dict], trades: List[BTTrade]) -> int:
        """保存到数据库，返回 backtest_id"""
        conn = db.get_connection()
        cursor = conn.cursor()

        trades_json = json.dumps([
            {
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "side": t.side,
                "entry_price": round(t.entry_price, 4),
                "exit_price": round(t.exit_price, 4),
                "amount": round(t.amount, 8),
                "pnl": round(t.pnl, 4),
                "pnl_pct": round(t.pnl_pct, 2),
                "fee": round(t.fee, 4),
                "bars_held": t.bars_held,
                "exit_reason": t.exit_reason,
            } for t in trades
        ])

        strat_name = STRATEGY_INFO.get(cfg.strategy_type, {}).get("name", cfg.strategy_type)

        cursor.execute("""
            INSERT INTO pro_backtest_results
            (strategy_type, strategy_name, exchange, symbol, timeframe,
             start_date, end_date, initial_capital, final_capital,
             total_return, annual_return, max_drawdown,
             sharpe_ratio, sortino_ratio, calmar_ratio,
             win_rate, profit_factor,
             total_trades, winning_trades, losing_trades,
             avg_win, avg_loss, largest_win, largest_loss, avg_holding_bars,
             trades_json, strategy_config, risk_config, status)
            VALUES (?,?,?,?,?, ?,?,?,?, ?,?,?, ?,?,?, ?,?, ?,?,?, ?,?,?,?,?, ?,?,?,?)
        """, (
            cfg.strategy_type, strat_name,
            cfg.exchange, cfg.symbol, cfg.timeframe,
            cfg.start_date, cfg.end_date,
            metrics.get("initial_capital", cfg.initial_capital),
            metrics.get("final_capital"),
            metrics.get("total_return"),
            metrics.get("annual_return"),
            metrics.get("max_drawdown"),
            metrics.get("sharpe_ratio"),
            metrics.get("sortino_ratio"),
            metrics.get("calmar_ratio"),
            metrics.get("win_rate"),
            metrics.get("profit_factor"),
            metrics.get("total_trades"),
            metrics.get("winning_trades"),
            metrics.get("losing_trades"),
            metrics.get("avg_win"),
            metrics.get("avg_loss"),
            metrics.get("largest_win"),
            metrics.get("largest_loss"),
            metrics.get("avg_holding_bars"),
            trades_json,
            json.dumps(cfg.strategy_config) if cfg.strategy_config else None,
            json.dumps(cfg.risk_config) if cfg.risk_config else None,
            "completed",
        ))

        backtest_id = cursor.lastrowid

        # 权益曲线：每 N 条采样一次防止数据量过大
        sample_step = max(1, len(equity_curve) // 2000)  # 最多保存 2000 个点
        eq_data = []
        for idx, ec in enumerate(equity_curve):
            if idx % sample_step == 0 or idx == len(equity_curve) - 1:
                eq_data.append((
                    backtest_id,
                    ec["bar_index"],
                    ec["timestamp"],
                    round(ec["equity"], 4),
                    round(ec["cash"], 4),
                    round(ec["position_value"], 4),
                    round(ec.get("drawdown_pct", 0), 4),
                ))

        cursor.executemany("""
            INSERT INTO pro_backtest_equity
            (backtest_id, bar_index, timestamp, equity, cash, position_value, drawdown_pct)
            VALUES (?,?,?,?,?,?,?)
        """, eq_data)

        conn.commit()
        conn.close()

        logger.info(f"  回测结果已保存 backtest_id={backtest_id}, "
                     f"权益点={len(eq_data)}, 交易={len(trades)}")
        return backtest_id


# ============================================================
# 查询工具函数 (供 API 层调用)
# ============================================================

def get_all_pro_backtests(limit: int = 50) -> List[Dict]:
    """获取所有 Pro 回测结果（摘要）"""
    ensure_tables()
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, strategy_type, strategy_name, exchange, symbol, timeframe,
               start_date, end_date, initial_capital, final_capital,
               total_return, annual_return, max_drawdown,
               sharpe_ratio, sortino_ratio, calmar_ratio,
               win_rate, profit_factor,
               total_trades, winning_trades, losing_trades,
               avg_win, avg_loss, largest_win, largest_loss, avg_holding_bars,
               status, created_at
        FROM pro_backtest_results
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pro_backtest_detail(backtest_id: int) -> Optional[Dict]:
    """获取单条回测详情（含交易明细）"""
    ensure_tables()
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM pro_backtest_results WHERE id = ?
    """, (backtest_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    result = dict(row)
    if result.get("trades_json"):
        result["trades"] = json.loads(result["trades_json"])
        del result["trades_json"]
    if result.get("strategy_config"):
        result["strategy_config"] = json.loads(result["strategy_config"])
    if result.get("risk_config"):
        result["risk_config"] = json.loads(result["risk_config"])
    conn.close()
    return result


def get_pro_backtest_equity(backtest_id: int) -> List[Dict]:
    """获取权益曲线"""
    ensure_tables()
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT bar_index, timestamp, equity, cash, position_value, drawdown_pct
        FROM pro_backtest_equity
        WHERE backtest_id = ?
        ORDER BY bar_index
    """, (backtest_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_by_strategy() -> List[Dict]:
    """每个策略取最新一次回测结果（用于一页对比）"""
    ensure_tables()
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.*
        FROM pro_backtest_results r
        INNER JOIN (
            SELECT strategy_type, MAX(id) as max_id
            FROM pro_backtest_results
            GROUP BY strategy_type
        ) latest ON r.id = latest.max_id
        ORDER BY r.total_return DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d.pop("trades_json", None)
        d.pop("strategy_config", None)
        d.pop("risk_config", None)
        results.append(d)
    return results


# 全局引擎实例
pro_backtest_engine = ProBacktestEngine()
