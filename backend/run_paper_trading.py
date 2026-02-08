#!/usr/bin/env python3
"""
BitPro 模拟盘独立运行脚本
============================
直接运行自适应布林带策略的模拟盘交易, 独立于 FastAPI 进程。
所有信号和事件都会存入 SQLite 数据库。

用法:
    python run_paper_trading.py

停止: Ctrl+C
"""
import os
import sys
import asyncio
import signal
import json
import time
import logging
from datetime import datetime

# 设置代理
os.environ.setdefault('HTTP_PROXY', 'http://127.0.0.1:7890')
os.environ.setdefault('HTTPS_PROXY', 'http://127.0.0.1:7890')

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.auto_trader import AutoTrader, TraderState
from app.exchange import exchange_manager

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('paper_trading.log', encoding='utf-8'),
    ]
)
logger = logging.getLogger('paper_trading')

# ====================================
# 配置
# ====================================
CONFIG = {
    'exchange': 'okx',
    'strategy_type': 'adaptive_bollinger_live',
    'symbol': 'BTC/USDT',
    'timeframe': '4h',
    'initial_equity': 1000.0,
    'dry_run': True,           # 模拟模式, 不实际下单
    'loop_interval': 60,       # 每60秒检查一次
    'risk_config': {
        'risk_per_trade_pct': 0.03,
        'max_daily_loss_pct': 0.05,
        'max_total_drawdown_pct': 0.15,
    },
}


# 优雅退出
shutdown_event = asyncio.Event()

def signal_handler(sig, frame):
    logger.info(f'收到退出信号 ({sig}), 正在停止...')
    shutdown_event.set()


async def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print()
    print('╔══════════════════════════════════════════════╗')
    print('║   BitPro 模拟盘交易系统                       ║')
    print('║   策略: 自适应布林带 ★Phase3                    ║')
    print('║   交易所: OKX  |  模式: dry_run (不下单)        ║')
    print('╚══════════════════════════════════════════════╝')
    print()
    
    # 初始化交易所
    logger.info('初始化交易所连接...')
    exchange_manager.init_exchanges()
    okx = exchange_manager.get_exchange('okx')
    if not okx:
        logger.error('OKX 交易所初始化失败！')
        return
    logger.info('OKX 交易所连接成功')
    
    # 测试获取K线
    try:
        test_klines = okx.fetch_ohlcv('BTC/USDT', '4h', limit=5)
        if test_klines:
            logger.info(f'BTC/USDT 4h 最新价格: ${test_klines[-1]["close"]:,.2f}')
        else:
            logger.warning('无法获取K线数据，但继续运行')
    except Exception as e:
        logger.warning(f'K线测试失败: {e}')
    
    # 创建并配置 AutoTrader
    trader = AutoTrader()
    
    strategy_config = {}
    strategy_config['symbol'] = CONFIG['symbol']
    
    trader.configure(
        exchange=CONFIG['exchange'],
        strategy_type=CONFIG['strategy_type'],
        symbol=CONFIG['symbol'],
        timeframe=CONFIG['timeframe'],
        initial_equity=CONFIG['initial_equity'],
        strategy_config=strategy_config,
        risk_config=CONFIG['risk_config'],
        loop_interval=CONFIG['loop_interval'],
        dry_run=CONFIG['dry_run'],
    )
    
    logger.info(f'配置完成: {CONFIG["strategy_type"]} on {CONFIG["exchange"]} {CONFIG["symbol"]} {CONFIG["timeframe"]}')
    logger.info(f'初始资金: ${CONFIG["initial_equity"]:,.2f}  |  模式: {"模拟" if CONFIG["dry_run"] else "实盘"}')
    logger.info(f'循环间隔: {CONFIG["loop_interval"]}s')
    logger.info('---')
    
    # 启动
    await trader.start()
    logger.info('模拟盘已启动, 等待策略信号...')
    logger.info('按 Ctrl+C 停止')
    print()
    
    # 主循环 - 定期打印状态
    cycle = 0
    while not shutdown_event.is_set():
        await asyncio.sleep(30)
        cycle += 1
        
        if trader.state != TraderState.RUNNING:
            logger.warning(f'系统状态异常: {trader.state.value}, 尝试重启...')
            try:
                await trader.start()
            except:
                pass
            continue
        
        # 每5分钟打印一次状态摘要
        if cycle % 10 == 0:
            status = trader.get_status()
            events = status.get('recent_events', [])
            signal_events = [e for e in events if e.get('type') in ('signal', 'order', 'close')]
            
            logger.info(
                f'[状态] 运行: {status["uptime"]} | '
                f'资金: ${status.get("equity", {}).get("current", 0):,.2f} | '
                f'信号: {len(signal_events)} | '
                f'交易: {status.get("performance", {}).get("totalTrades", 0)}'
            )
    
    # 停止
    logger.info('正在停止模拟盘...')
    await trader.stop()
    
    # 打印最终统计
    status = trader.get_status()
    perf = status.get('performance', {})
    
    print()
    print('╔══════════════════════════════════════╗')
    print('║          模拟盘运行报告               ║')
    print('╠══════════════════════════════════════╣')
    print(f'  运行时长: {status["uptime"]}')
    print(f'  总交易: {perf.get("totalTrades", 0)}')
    print(f'  盈利/亏损: {perf.get("winningTrades", 0)}/{perf.get("losingTrades", 0)}')
    print(f'  总PnL: ${perf.get("totalPnl", 0):,.2f} ({perf.get("totalPnlPct", 0):+.2f}%)')
    print(f'  最大回撤: {perf.get("maxDrawdown", 0):.2f}%')
    print('╚══════════════════════════════════════╝')
    
    # 检查数据库记录
    try:
        from app.db.local_db import db_instance as db
        conn = db.get_connection()
        cur = conn.execute('SELECT COUNT(*) as cnt FROM trading_events WHERE dry_run = 1')
        total = cur.fetchone()['cnt']
        logger.info(f'数据库中共 {total} 条模拟盘事件记录')
        conn.close()
    except:
        pass
    
    logger.info('模拟盘已安全停止')


if __name__ == '__main__':
    asyncio.run(main())
