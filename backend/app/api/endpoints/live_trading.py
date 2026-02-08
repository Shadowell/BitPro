"""
实盘交易 API (Phase 5)
=====================
整合 AutoTrader + Phase3策略 + Telegram通知 + 监控仪表盘

端点:
  POST /configure     — 配置实盘系统 (推荐: adaptive_bollinger_live)
  POST /start         — 启动实盘
  POST /stop          — 停止实盘
  GET  /dashboard     — 实时监控仪表盘
  GET  /signals       — 信号历史
  POST /test_telegram — 测试Telegram推送
  POST /pre_flight    — 实盘前飞行检查
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict, Any
from pydantic import BaseModel
import logging
import time
from datetime import datetime

from app.services.auto_trader import AutoTrader, TraderState
from app.services.telegram_notifier import telegram_notifier
from app.services.signal_notifier import pre_flight_checklist

router = APIRouter()
logger = logging.getLogger(__name__)

# 独立的实盘/模拟盘 AutoTrader 实例
# 与 auto_trade.py 的 auto_trader 隔离，避免前端页面自动配置覆盖
live_trader = AutoTrader()


# ============================================
# 策略类型解析
# ============================================

def _resolve_strategy_type(strategy_input: str) -> str:
    """
    将前端传来的策略标识解析为 auto_strategies 的策略类型 key。
    支持:
      - 数字ID (如 "6") → 从数据库查 config.strategy_key
      - db_XX 格式 (兼容旧前端) → 同上
      - 直接 key (如 "smart_trend") → 原样返回
    """
    from app.db.local_db import db_instance as db
    import json

    # 尝试解析为数据库 ID
    raw = strategy_input.replace('db_', '') if strategy_input.startswith('db_') else strategy_input
    try:
        db_id = int(raw)
        strategy = db.get_strategy_by_id(db_id)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"策略 #{db_id} 不存在")

        cfg = strategy.get('config') or {}
        strategy_key = cfg.get('strategy_key', '')

        if strategy_key:
            logger.info(f"策略 '{strategy['name']}' (ID={db_id}) → '{strategy_key}'")
            return strategy_key

        # config 里没有 key，用名称兜底
        raise HTTPException(
            status_code=400,
            detail=f"策略 '{strategy['name']}' 缺少 strategy_key 配置，无法用于模拟盘"
        )
    except ValueError:
        pass

    # 不是数字，当作直接的 strategy key
    return strategy_input


# ============================================
# 请求模型
# ============================================

class LiveTradingConfig(BaseModel):
    """实盘配置"""
    exchange: str = "okx"
    strategy_type: str = "adaptive_bollinger_live"  # Phase3最优
    symbol: str = "BTC/USDT"
    timeframe: str = "4h"
    initial_equity: float = 1000.0
    dry_run: bool = True           # 默认模拟模式 (dry_run=True不实际下单)
    loop_interval: int = 60        # 每60秒检查一次
    strategy_config: Optional[Dict[str, Any]] = None
    risk_config: Optional[Dict[str, Any]] = None


class TelegramTestRequest(BaseModel):
    """Telegram测试请求"""
    message: str = "BitPro 实盘系统测试消息"


# ============================================
# 系统控制
# ============================================

@router.post("/configure")
async def configure_live_trading(config: LiveTradingConfig):
    """
    配置实盘交易系统

    推荐配置:
    - strategy_type: adaptive_bollinger_live (Phase3最优)
    - symbol: BTC/USDT
    - timeframe: 4h
    - dry_run: true (先用模拟模式验证)
    """
    try:
        # 解析策略类型 — 支持数据库策略ID (数字) 和直接 key
        strategy_type = _resolve_strategy_type(config.strategy_type)

        # 合并策略配置
        strategy_config = config.strategy_config or {}
        strategy_config['symbol'] = config.symbol

        risk_config = config.risk_config or {
            'risk_per_trade_pct': 0.03,
            'max_daily_loss_pct': 0.05,
            'max_total_drawdown_pct': 0.15,
        }
        # 兼容前端字段名映射
        if 'max_total_loss_pct' in risk_config and 'max_total_drawdown_pct' not in risk_config:
            risk_config['max_total_drawdown_pct'] = risk_config.pop('max_total_loss_pct')

        live_trader.configure(
            exchange=config.exchange,
            strategy_type=strategy_type,
            symbol=config.symbol,
            timeframe=config.timeframe,
            initial_equity=config.initial_equity,
            strategy_config=strategy_config,
            risk_config=risk_config,
            loop_interval=config.loop_interval,
            dry_run=config.dry_run,
        )

        # Telegram 通知
        await telegram_notifier.notify_system(
            '系统配置完成',
            f'策略={config.strategy_type}, 品种={config.symbol}, '
            f'资金=${config.initial_equity}, 模式={"模拟" if config.dry_run else "实盘"}'
        )

        return {
            'status': 'ok',
            'message': '实盘系统配置完成',
            'config': {
                'strategy': config.strategy_type,
                'symbol': config.symbol,
                'timeframe': config.timeframe,
                'equity': config.initial_equity,
                'dry_run': config.dry_run,
                'mode': '模拟模式' if config.dry_run else '⚠️ 实盘模式',
            },
        }
    except Exception as e:
        logger.error(f"配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/start")
async def start_live_trading():
    """启动实盘交易"""
    try:
        await live_trader.start()
        await telegram_notifier.notify_system(
            '实盘系统启动',
            f'策略={live_trader._strategy.name if live_trader._strategy else "?"}, '
            f'品种={live_trader._symbol}'
        )
        return {'status': 'ok', 'message': '实盘系统已启动'}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/stop")
async def stop_live_trading():
    """停止实盘交易"""
    try:
        await live_trader.stop()
        await telegram_notifier.notify_system('实盘系统停止')
        return {'status': 'ok', 'message': '实盘系统已停止'}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/pause")
async def pause_live_trading():
    """暂停"""
    await live_trader.pause()
    await telegram_notifier.notify_system('实盘系统暂停')
    return {'status': 'ok'}


@router.post("/resume")
async def resume_live_trading():
    """恢复"""
    await live_trader.resume()
    await telegram_notifier.notify_system('实盘系统恢复')
    return {'status': 'ok'}


# ============================================
# 监控仪表盘
# ============================================

@router.get("/dashboard")
async def get_dashboard():
    """
    实盘监控仪表盘

    返回:
    - system: 系统状态
    - equity: 资金信息
    - position: 当前持仓
    - performance: 绩效指标
    - risk: 风控状态
    - signals: 最近信号
    - telegram: 通知状态
    """
    status = live_trader.get_status()

    # 增强仪表盘
    dashboard = {
        'system': {
            'state': status['state'],
            'uptime': status.get('uptime', '0m'),
            'exchange': status.get('exchange', '-'),
            'symbol': status.get('symbol', '-'),
            'timeframe': status.get('timeframe', '-'),
            'strategy': status.get('strategy', '-'),
            'dry_run': status.get('dry_run', True),
            'mode': '🟡 模拟模式' if status.get('dry_run', True) else '🔴 实盘模式',
        },
        'equity': status.get('equity', {}),
        'performance': status.get('performance', {}),
        'risk': status.get('risk', {}),
        'recent_events': status.get('recent_events', []),
        'telegram': {
            'enabled': telegram_notifier.enabled,
            'messages_sent': len([m for m in telegram_notifier.get_message_history() if m.get('sent')]),
            'recent': telegram_notifier.get_message_history(5),
        },
    }

    return dashboard


@router.get("/events")
async def get_events(
    limit: int = Query(50, ge=1, le=200),
    event_type: Optional[str] = Query(None),
):
    """获取交易事件"""
    return live_trader.get_events(limit, event_type)


@router.get("/equity_curve")
async def get_equity_curve():
    """获取权益曲线"""
    return live_trader.get_equity_curve()


@router.get("/strategy_info")
async def get_strategy_info():
    """获取当前策略信息"""
    return live_trader.get_strategy_info()


# ============================================
# Telegram 通知
# ============================================

@router.post("/test_telegram")
async def test_telegram(request: TelegramTestRequest):
    """测试 Telegram 推送"""
    success = await telegram_notifier.send_message(
        f"<b>🔔 测试消息</b>\n{request.message}\n\n"
        f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    return {
        'success': success,
        'enabled': telegram_notifier.enabled,
        'message': '发送成功' if success else (
            '未配置 TELEGRAM_BOT_TOKEN/CHAT_ID' if not telegram_notifier.enabled
            else '发送失败，检查网络或token'
        ),
    }


@router.get("/telegram_history")
async def get_telegram_history(limit: int = Query(50, ge=1, le=200)):
    """获取 Telegram 消息历史"""
    return telegram_notifier.get_message_history(limit)


# ============================================
# 飞行检查
# ============================================

class PreFlightConfig(BaseModel):
    strategy: str = "adaptive_bollinger"
    symbol: str = "BTC/USDT"
    timeframe: str = "4h"
    capital_pct: float = 0.10
    total_capital: float = 10000.0


@router.post("/pre_flight")
async def run_pre_flight(config: PreFlightConfig):
    """实盘前飞行检查"""
    try:
        result = pre_flight_checklist(
            strategy_name=config.strategy,
            symbol=config.symbol,
            timeframe=config.timeframe,
            capital_pct=config.capital_pct,
            total_capital=config.total_capital,
        )

        # Telegram 通知结果
        status_text = '✅ 全部通过' if result['all_passed'] else '⚠️ 有未通过项'
        await telegram_notifier.notify_system(
            f'飞行检查: {status_text}',
            '\n'.join(f"{'✅' if c['passed'] else '❌'} {c['item']}" for c in result['checks'])
        )

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 可用策略
# ============================================

@router.get("/strategies")
async def list_strategies():
    """列出所有可用策略 — 统一从数据库读取"""
    from app.db.local_db import db_instance as db
    import json

    strategy_list = []
    try:
        conn = db.get_connection()
        cursor = conn.cursor()

        # 获取所有非 error 策略
        cursor.execute('''
            SELECT id, name, description, config, status, exchange, symbols
            FROM strategies WHERE status != 'error'
            ORDER BY id
        ''')
        rows = cursor.fetchall()

        # 获取最新回测数据
        bt_map = {}
        cursor.execute('''
            SELECT strategy_id, total_return, annual_return, max_drawdown,
                   sharpe_ratio, win_rate, total_trades, profit_factor
            FROM backtest_results
            WHERE id IN (SELECT MAX(id) FROM backtest_results GROUP BY strategy_id)
        ''')
        for bt in cursor.fetchall():
            bt_map[bt['strategy_id']] = {
                'total_return': bt['total_return'],
                'annual_return': bt['annual_return'],
                'max_drawdown': bt['max_drawdown'],
                'sharpe_ratio': bt['sharpe_ratio'],
                'win_rate': bt['win_rate'],
                'total_trades': bt['total_trades'],
                'profit_factor': bt['profit_factor'],
            }
        conn.close()

        for row in rows:
            sid = row['id']
            cfg = {}
            if row['config']:
                try:
                    cfg = json.loads(row['config']) if isinstance(row['config'], str) else row['config']
                except Exception:
                    pass

            item = {
                'id': sid,
                'name': row['name'],
                'description': row['description'] or '',
                'risk_level': cfg.get('risk_level', '中'),
                'timeframe': cfg.get('timeframe', '4h'),
                'suitable_for': cfg.get('suitable_for', ''),
                'recommended': cfg.get('recommended', False),
                'strategy_key': cfg.get('strategy_key', ''),
            }
            bt = bt_map.get(sid)
            if bt:
                item['backtest'] = bt
            strategy_list.append(item)

    except Exception as e:
        logger.error(f"加载策略失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    # 找推荐策略 (回测收益最高)
    best_id = None
    best_return = -999
    for s in strategy_list:
        if s.get('recommended'):
            best_id = s['id']
            break
        bt = s.get('backtest')
        if bt:
            r = bt.get('total_return', -999) or -999
            if r > best_return:
                best_return = r
                best_id = s['id']

    return {
        'strategies': strategy_list,
        'recommended': best_id,
        'total': len(strategy_list),
    }
