"""
历史数据同步服务
负责从交易所批量拉取历史K线/资金费率数据，存入本地 SQLite
支持增量同步、断点续传、定时调度
"""
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

from app.db.local_db import db_instance as db
from app.exchange import exchange_manager

logger = logging.getLogger(__name__)


# ============================================
# 默认同步配置
# ============================================

# 默认同步的交易对
DEFAULT_SYMBOLS = [
    'BTC/USDT',
    'ETH/USDT',
    'SOL/USDT',
    'BNB/USDT',
    'XRP/USDT',
    'DOGE/USDT',
    'ADA/USDT',
    'AVAX/USDT',
    'LINK/USDT',
    'DOT/USDT',
    'ZAMA/USDT',
]

# 默认同步的时间周期
DEFAULT_TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d']

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

# 默认回溯天数（首次同步时拉取多少天的历史数据）
DEFAULT_HISTORY_DAYS = 365  # 1年

# 每次 API 请求的最大K线数 (OKX 单次限制 300)
MAX_KLINES_PER_REQUEST = 300

# API 请求间隔（秒），避免触发限流
API_REQUEST_DELAY = 0.15

# 单个任务最大连续错误次数
MAX_CONSECUTIVE_ERRORS = 5


class SyncStatus(str, Enum):
    """同步状态"""
    IDLE = "idle"
    SYNCING = "syncing"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class SyncProgress:
    """单个同步任务进度"""
    exchange: str
    symbol: str
    timeframe: str
    status: SyncStatus = SyncStatus.IDLE
    total_fetched: int = 0
    total_inserted: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error: Optional[str] = None


@dataclass
class SyncJobResult:
    """同步任务汇总结果"""
    exchange: str
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    total_symbols: int = 0
    total_timeframes: int = 0
    total_records_fetched: int = 0
    total_records_inserted: int = 0
    errors: List[str] = field(default_factory=list)
    progress: List[SyncProgress] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.completed_at is None:
            return "running"
        if self.errors:
            return "completed_with_errors"
        return "completed"


class DataSyncService:
    """数据同步服务"""

    def __init__(self):
        self._running = False
        self._current_job: Optional[SyncJobResult] = None
        self._lock = asyncio.Lock()
        self._scheduler = None  # APScheduler 实例，后续集成

    # ============================================
    # 核心同步逻辑
    # ============================================

    async def sync_klines(
        self,
        exchange_name: str,
        symbol: str,
        timeframe: str,
        start_date: str = None,
        end_date: str = None,
        history_days: int = DEFAULT_HISTORY_DAYS,
    ) -> SyncProgress:
        """
        同步单个交易对的K线数据

        Args:
            exchange_name: 交易所名称
            symbol: 交易对 (如 BTC/USDT)
            timeframe: K线周期 (如 1h, 4h, 1d)
            start_date: 起始日期 (YYYY-MM-DD)，不传则使用上次同步位置或默认回溯
            end_date: 结束日期 (YYYY-MM-DD)，不传则同步到当前
            history_days: 首次同步回溯天数
        """
        progress = SyncProgress(
            exchange=exchange_name,
            symbol=symbol,
            timeframe=timeframe,
            status=SyncStatus.SYNCING,
            start_time=datetime.now(),
        )

        try:
            exchange = exchange_manager.get_exchange(exchange_name)
            if not exchange:
                raise ValueError(f"交易所 {exchange_name} 不可用")

            interval_ms = TIMEFRAME_MS.get(timeframe, 3600000)
            now_ms = int(datetime.now().timestamp() * 1000)

            # 确定起始时间：优先使用参数 > 上次同步位置 > 默认回溯
            if start_date:
                start_ms = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
            else:
                # 检查上次同步位置
                meta = db.get_sync_metadata(exchange_name, symbol, timeframe, 'kline')
                if meta and meta.get('last_timestamp'):
                    # 从上次位置的下一根K线开始（增量同步）
                    start_ms = meta['last_timestamp'] + interval_ms
                else:
                    # 首次同步，回溯 history_days 天
                    start_ms = now_ms - history_days * 24 * 3600 * 1000

            # 确定结束时间
            if end_date:
                end_ms = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
            else:
                end_ms = now_ms

            # 如果起始已经超过结束，说明数据已是最新
            if start_ms >= end_ms:
                logger.info(f"[{exchange_name}] {symbol} {timeframe} 数据已是最新")
                progress.status = SyncStatus.COMPLETED
                progress.end_time = datetime.now()
                return progress

            # 更新同步状态为 syncing
            db.update_sync_metadata(
                exchange_name, symbol, timeframe, 'kline',
                status='syncing'
            )

            logger.info(
                f"[{exchange_name}] 开始同步 {symbol} {timeframe} "
                f"从 {datetime.fromtimestamp(start_ms/1000).strftime('%Y-%m-%d %H:%M')} "
                f"到 {datetime.fromtimestamp(end_ms/1000).strftime('%Y-%m-%d %H:%M')}"
            )

            # 分批拉取数据
            current_ms = start_ms
            batch_count = 0
            consecutive_errors = 0

            while current_ms < end_ms:
                try:
                    klines = exchange.fetch_ohlcv(
                        symbol, timeframe,
                        limit=MAX_KLINES_PER_REQUEST,
                        since=current_ms
                    )

                    if not klines:
                        logger.debug(f"[{exchange_name}] {symbol} {timeframe} 无更多数据 (since={current_ms})")
                        break

                    # 过滤超出结束时间的数据
                    klines = [k for k in klines if k['timestamp'] <= end_ms]

                    if not klines:
                        break

                    # 检测是否卡在同一位置（OKX 有时会返回重复数据）
                    first_ts = klines[0]['timestamp']
                    last_ts = klines[-1]['timestamp']
                    if last_ts <= current_ms and len(klines) < MAX_KLINES_PER_REQUEST:
                        logger.debug(f"[{exchange_name}] {symbol} {timeframe} 数据不再前进，结束")
                        break

                    # 批量写入数据库
                    inserted = db.insert_klines(exchange_name, symbol, timeframe, klines)

                    progress.total_fetched += len(klines)
                    progress.total_inserted += inserted
                    batch_count += 1
                    consecutive_errors = 0  # 成功后重置错误计数

                    # 更新游标到最后一条数据的下一个时间戳
                    current_ms = last_ts + interval_ms

                    # 每 20 批次或每 5000 条更新一次元数据并打印日志
                    if batch_count % 20 == 0:
                        db.update_sync_metadata(
                            exchange_name, symbol, timeframe, 'kline',
                            last_timestamp=last_ts,
                            total_records=progress.total_fetched,
                        )
                        logger.info(
                            f"[{exchange_name}] {symbol} {timeframe} "
                            f"已同步 {progress.total_fetched} 条 "
                            f"(到 {datetime.fromtimestamp(last_ts/1000).strftime('%Y-%m-%d %H:%M')})"
                        )

                    # 如果返回数据少于请求数，说明到头了
                    if len(klines) < MAX_KLINES_PER_REQUEST:
                        break

                    # 避免触发 API 限流
                    await asyncio.sleep(API_REQUEST_DELAY)

                except Exception as e:
                    consecutive_errors += 1
                    logger.warning(
                        f"[{exchange_name}] {symbol} {timeframe} "
                        f"批次 {batch_count} 拉取失败 (连续第{consecutive_errors}次): {e}"
                    )
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        logger.error(
                            f"[{exchange_name}] {symbol} {timeframe} "
                            f"连续失败 {MAX_CONSECUTIVE_ERRORS} 次，跳过"
                        )
                        progress.error = f"连续失败 {MAX_CONSECUTIVE_ERRORS} 次: {e}"
                        break
                    # 指数退避重试
                    await asyncio.sleep(min(2 ** consecutive_errors, 30))

            # 同步完成，更新最终元数据
            time_range = db.get_kline_time_range(exchange_name, symbol, timeframe)
            total_count = db.get_kline_count(exchange_name, symbol, timeframe)

            db.update_sync_metadata(
                exchange_name, symbol, timeframe, 'kline',
                first_timestamp=time_range['first_timestamp'] if time_range else None,
                last_timestamp=time_range['last_timestamp'] if time_range else None,
                total_records=total_count,
                status='completed',
                last_sync_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                error_message=None,
            )

            progress.status = SyncStatus.COMPLETED
            progress.end_time = datetime.now()

            logger.info(
                f"[{exchange_name}] {symbol} {timeframe} 同步完成: "
                f"拉取 {progress.total_fetched} 条, 新增 {progress.total_inserted} 条, "
                f"本地总计 {total_count} 条"
            )

        except Exception as e:
            logger.error(f"[{exchange_name}] {symbol} {timeframe} 同步失败: {e}")
            progress.status = SyncStatus.ERROR
            progress.error = str(e)
            progress.end_time = datetime.now()

            db.update_sync_metadata(
                exchange_name, symbol, timeframe, 'kline',
                status='error',
                error_message=str(e),
            )

        return progress

    async def sync_all(
        self,
        exchange_name: str = 'okx',
        symbols: List[str] = None,
        timeframes: List[str] = None,
        history_days: int = DEFAULT_HISTORY_DAYS,
        start_date: str = None,
        end_date: str = None,
    ) -> SyncJobResult:
        """
        批量同步所有配置的交易对和时间周期

        Args:
            exchange_name: 交易所名称
            symbols: 要同步的交易对列表，None 则使用默认
            timeframes: 要同步的时间周期列表，None 则使用默认
            start_date: 起始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
        """
        async with self._lock:
            if self._running:
                logger.warning("已有同步任务在运行中，请稍后再试")
                if self._current_job:
                    return self._current_job
                return SyncJobResult(exchange=exchange_name)

            self._running = True

        symbols = symbols or DEFAULT_SYMBOLS
        timeframes = timeframes or DEFAULT_TIMEFRAMES

        job = SyncJobResult(
            exchange=exchange_name,
            total_symbols=len(symbols),
            total_timeframes=len(timeframes),
        )
        self._current_job = job

        date_range = f"{start_date} ~ {end_date}" if start_date else f"回溯 {history_days} 天"
        logger.info(
            f"========== 开始数据同步 ==========\n"
            f"交易所: {exchange_name}\n"
            f"交易对: {len(symbols)} 个\n"
            f"周期: {timeframes}\n"
            f"日期范围: {date_range}"
        )

        try:
            for symbol in symbols:
                for timeframe in timeframes:
                    progress = await self.sync_klines(
                        exchange_name, symbol, timeframe,
                        history_days=history_days,
                        start_date=start_date,
                        end_date=end_date,
                    )
                    job.progress.append(progress)
                    job.total_records_fetched += progress.total_fetched
                    job.total_records_inserted += progress.total_inserted

                    if progress.error:
                        job.errors.append(
                            f"{symbol} {timeframe}: {progress.error}"
                        )

        except Exception as e:
            logger.error(f"批量同步异常: {e}")
            job.errors.append(f"全局异常: {str(e)}")

        finally:
            job.completed_at = datetime.now()
            self._running = False

        elapsed = (job.completed_at - job.started_at).total_seconds()
        logger.info(
            f"========== 数据同步完成 ==========\n"
            f"耗时: {elapsed:.1f}s\n"
            f"总拉取: {job.total_records_fetched} 条\n"
            f"总新增: {job.total_records_inserted} 条\n"
            f"错误: {len(job.errors)} 个"
        )

        return job

    # ============================================
    # 增量日更新（定时调度用）
    # ============================================

    async def daily_update(self, exchange_name: str = 'okx'):
        """
        每日增量更新
        只同步自上次同步以来的新数据
        """
        logger.info(f"[定时任务] 开始每日增量更新: {exchange_name}")
        return await self.sync_all(
            exchange_name=exchange_name,
            history_days=7,  # 增量更新时只回溯7天（以防断档）
        )

    # ============================================
    # 状态查询
    # ============================================

    def get_sync_status(self) -> Dict[str, Any]:
        """获取当前同步状态"""
        meta_list = db.get_all_sync_metadata()

        # 汇总统计
        total_records = sum(m.get('total_records', 0) for m in meta_list)
        exchanges = list(set(m['exchange'] for m in meta_list))
        symbols = list(set(m['symbol'] for m in meta_list))

        return {
            'is_running': self._running,
            'current_job': {
                'exchange': self._current_job.exchange if self._current_job else None,
                'status': self._current_job.status if self._current_job else None,
                'total_fetched': self._current_job.total_records_fetched if self._current_job else 0,
                'total_inserted': self._current_job.total_records_inserted if self._current_job else 0,
                'errors': len(self._current_job.errors) if self._current_job else 0,
            } if self._current_job else None,
            'summary': {
                'total_records': total_records,
                'exchanges': exchanges,
                'symbols_count': len(symbols),
                'pairs': len(meta_list),
            },
            'details': meta_list,
        }

    def get_available_data(self, exchange: str = None) -> List[Dict]:
        """获取已同步的数据清单"""
        meta_list = db.get_all_sync_metadata(exchange)

        result = []
        for m in meta_list:
            first_ts = m.get('first_timestamp')
            last_ts = m.get('last_timestamp')
            result.append({
                'exchange': m['exchange'],
                'symbol': m['symbol'],
                'timeframe': m['timeframe'],
                'total_records': m.get('total_records', 0),
                'first_date': datetime.fromtimestamp(first_ts / 1000).strftime('%Y-%m-%d') if first_ts else None,
                'last_date': datetime.fromtimestamp(last_ts / 1000).strftime('%Y-%m-%d %H:%M') if last_ts else None,
                'status': m.get('status'),
                'last_sync_at': m.get('last_sync_at'),
            })

        return result


# 全局实例
data_sync_service = DataSyncService()
