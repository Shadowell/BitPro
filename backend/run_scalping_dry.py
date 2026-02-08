#!/usr/bin/env python3
"""
BTC/USDT 高频剥头皮策略 — Dry Run 实时监控
==========================================
独立运行脚本，不依赖 API 服务器，不受前端干扰。

使用方法:
    cd backend && source venv/bin/activate
    python run_scalping_dry.py
"""
import sys, os, time, json, signal as sig_mod
from datetime import datetime
from pathlib import Path

# 添加 backend 到 path
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

# 加载 .env 文件
from dotenv import load_dotenv
env_path = os.path.join(backend_dir, ".env")
load_dotenv(env_path, override=True)
print(f"📄 已加载 .env: {env_path}")
print(f"   HTTP_PROXY={os.environ.get('HTTP_PROXY', '未设置')}")
print(f"   OKX_TESTNET={os.environ.get('OKX_TESTNET', '未设置')}")

from app.exchange.okx import OKXExchange
from app.services.auto_strategies import create_strategy
from app.services.indicators import klines_to_arrays, RSI, BBANDS, VWAP, ATR

# 强制 flush print
import functools
print = functools.partial(print, flush=True)

# ============================================
# 配置
# ============================================
EXCHANGE = "okx"
SYMBOL = "BTC/USDT"
TIMEFRAME = "15m"
INITIAL_EQUITY = 66.0
LOOP_INTERVAL = 30  # 秒
MAX_CYCLES = 5      # 先跑 5 轮验证

# ============================================
# 全局变量
# ============================================
running = True
trades = []
signals = []
equity = INITIAL_EQUITY

def handle_signal(sig, frame):
    global running
    print("\n\n⛔ 收到退出信号，正在停止...")
    running = False

sig_mod.signal(sig_mod.SIGINT, handle_signal)
sig_mod.signal(sig_mod.SIGTERM, handle_signal)


def print_header():
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   BTC/USDT 高频剥头皮策略 | Dry Run 实时监控            ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║  交易所: {EXCHANGE:8s}  |  周期: {TIMEFRAME:6s}  |  模式: 模拟   ║")
    print(f"║  初始资金: {INITIAL_EQUITY:.2f} USDT                              ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()


def print_market_snapshot(klines):
    """打印当前市场快照"""
    arr = klines_to_arrays(klines)
    close = arr['close']
    high = arr['high']
    low = arr['low']
    volume = arr['volume']
    
    cur_price = close[-1]
    prev_price = close[-2] if len(close) > 1 else cur_price
    change_pct = (cur_price - prev_price) / prev_price * 100
    
    rsi = RSI(close, 7)
    rsi_val = rsi[-1] if len(rsi) > 0 else 0
    
    upper, middle, lower = BBANDS(close, 20, 2.0)
    bb_width = (upper[-1] - lower[-1]) / middle[-1] * 100 if middle[-1] > 0 else 0
    
    atr = ATR(high, low, close, 14)
    atr_val = atr[-1] if len(atr) > 0 else 0
    
    arrow = "↑" if change_pct > 0 else "↓" if change_pct < 0 else "→"
    
    print(f"  📊 BTC: ${cur_price:,.1f} {arrow} ({change_pct:+.2f}%)")
    print(f"  📈 RSI(7): {rsi_val:.1f}  |  BB宽度: {bb_width:.2f}%  |  ATR: ${atr_val:,.1f}")
    print(f"  📉 布林: 上轨=${upper[-1]:,.1f}  中轨=${middle[-1]:,.1f}  下轨=${lower[-1]:,.1f}")
    print(f"  📊 成交量: {volume[-1]:,.0f} BTC")


def main():
    global running, equity, trades, signals
    
    print_header()
    
    # 初始化 OKX 交易所 (直接初始化，不走 manager，加速启动)
    print("🔌 初始化 OKX 交易所...")
    ex = OKXExchange()
    ex.initialize()
    ex.load_markets()
    print(f"✅ OKX 连接成功")
    
    # 初始化策略
    print("🧠 初始化剥头皮策略...")
    strategy = create_strategy("scalping", {
        "symbol": SYMBOL,
        "risk": {
            "risk_per_trade_pct": 0.01,
            "max_daily_loss_pct": 0.05,
            "default_stop_loss_pct": 0.015,
            "default_take_profit_pct": 0.02,
            "max_position_pct": 0.3,
        }
    })
    strategy.initialize(INITIAL_EQUITY)
    print("✅ 策略初始化完成")
    print()
    print(f"🚀 开始实时监控 (每 {LOOP_INTERVAL}s 一轮, 最多 {MAX_CYCLES} 轮)")
    print("=" * 60)
    
    cycle = 0
    start_time = time.time()
    
    while running and cycle < MAX_CYCLES:
        cycle += 1
        now = datetime.now().strftime("%H:%M:%S")
        
        print(f"\n─── 第 {cycle}/{MAX_CYCLES} 轮 [{now}] ───")
        
        # 获取市场数据
        try:
            klines = ex.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=200)
        except Exception as e:
            print(f"  ⚠️  获取K线失败: {e}")
            time.sleep(LOOP_INTERVAL)
            continue
        
        if not klines or len(klines) < 30:
            print("  ⚠️  K线数据不足")
            time.sleep(LOOP_INTERVAL)
            continue
        
        # 打印市场快照
        print_market_snapshot(klines)
        
        # 执行策略
        try:
            result = strategy.execute(klines, equity)
        except Exception as e:
            print(f"  ⚠️  策略执行异常: {e}")
            time.sleep(LOOP_INTERVAL)
            continue
        
        action = result.get("action", "hold")
        confidence = result.get("confidence", 0)
        sig = result.get("signal", {})
        reason = sig.get("reason", result.get("reason", ""))
        
        if action == "hold":
            print(f"  ⏸️  信号: HOLD — {reason or '无触发条件'}")
        elif action == "buy":
            price = klines[-1]['close']
            sl = result.get("stop_loss")
            tp = result.get("take_profit")
            print(f"  🟢 信号: BUY  置信度={confidence:.0%}")
            print(f"     价格: ${price:,.1f}  止损: ${sl:,.1f}  止盈: ${tp:,.1f}" if sl and tp else f"     价格: ${price:,.1f}")
            print(f"     原因: {reason}")
            signals.append({
                "cycle": cycle, "time": now, "action": "BUY",
                "price": price, "confidence": confidence, "reason": reason,
            })
        elif action == "sell":
            price = klines[-1]['close']
            sl = result.get("stop_loss")
            tp = result.get("take_profit")
            print(f"  🔴 信号: SELL 置信度={confidence:.0%}")
            print(f"     价格: ${price:,.1f}  止损: ${sl:,.1f}  止盈: ${tp:,.1f}" if sl and tp else f"     价格: ${price:,.1f}")
            print(f"     原因: {reason}")
            signals.append({
                "cycle": cycle, "time": now, "action": "SELL",
                "price": price, "confidence": confidence, "reason": reason,
            })
        elif action == "close":
            pnl = result.get("pnl", 0)
            equity += pnl
            print(f"  🔒 平仓: PnL={pnl:+.2f} USDT | 原因: {reason}")
            trades.append({"cycle": cycle, "time": now, "pnl": pnl})
        
        # 等待下一轮
        if cycle < MAX_CYCLES and running:
            time.sleep(LOOP_INTERVAL)
    
    # 结束总结
    elapsed = time.time() - start_time
    print()
    print("=" * 60)
    print("📋 运行总结")
    print("=" * 60)
    print(f"  运行时间: {elapsed/60:.1f} 分钟 ({cycle} 轮)")
    print(f"  初始资金: {INITIAL_EQUITY:.2f} USDT")
    print(f"  最终资金: {equity:.2f} USDT")
    print(f"  总信号数: {len(signals)}")
    
    if signals:
        print()
        print("  信号记录:")
        for s in signals:
            print(f"    [{s['time']}] {s['action']} @ ${s['price']:,.1f} | {s['confidence']:.0%} | {s['reason']}")
    
    if trades:
        print()
        total_pnl = sum(t['pnl'] for t in trades)
        wins = [t for t in trades if t['pnl'] > 0]
        print(f"  交易记录: {len(trades)} 笔")
        print(f"  总PnL: {total_pnl:+.2f} USDT")
        print(f"  胜率: {len(wins)/len(trades)*100:.0f}%")
    
    if not signals and not trades:
        print()
        print("  💡 未产生信号 — 当前市场条件未触发剥头皮策略的极值条件")
        print("     (RSI需要<20或>80, 且需要VWAP偏离确认)")
    
    print()
    print("✅ 监控结束")


if __name__ == "__main__":
    main()
