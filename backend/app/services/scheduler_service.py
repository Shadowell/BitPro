"""
定时调度服务
使用 APScheduler 管理定时任务：
- 每天凌晨自动同步最新K线数据
- 每小时检查数据完整性
"""
import asyncio
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


class SchedulerService:
    """定时调度服务"""

    def __init__(self):
        self._scheduler: AsyncIOScheduler = None
        self._running = False

    async def start(self):
        """启动调度器"""
        if self._running:
            return

        self._scheduler = AsyncIOScheduler(
            timezone='Asia/Shanghai',
            job_defaults={
                'coalesce': True,          # 错过的任务合并执行一次
                'max_instances': 1,         # 同一任务最多1个实例
                'misfire_grace_time': 3600, # 错过1小时内的任务仍会执行
            }
        )

        # ---- 注册定时任务 ----

        # 1. 每天凌晨 2:00 执行全量增量同步（OKX）
        self._scheduler.add_job(
            self._daily_sync_job,
            CronTrigger(hour=2, minute=0),
            id='daily_sync_okx',
            name='每日K线数据同步(OKX)',
            kwargs={'exchange_name': 'okx'},
        )

        # 3. 每 4 小时执行一次快速增量同步（只同步最近数据）
        self._scheduler.add_job(
            self._quick_sync_job,
            IntervalTrigger(hours=4),
            id='quick_sync',
            name='快速增量同步',
        )

        self._scheduler.start()
        self._running = True

        logger.info("定时调度服务已启动")
        self._log_scheduled_jobs()

    async def stop(self):
        """停止调度器"""
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("定时调度服务已停止")

    # ============================================
    # 定时任务实现
    # ============================================

    async def _daily_sync_job(self, exchange_name: str = 'okx'):
        """每日数据同步任务"""
        logger.info(f"[定时任务] 开始每日数据同步: {exchange_name}")
        try:
            from app.services.data_sync_service import data_sync_service
            await data_sync_service.daily_update(exchange_name)
            logger.info(f"[定时任务] 每日数据同步完成: {exchange_name}")
        except Exception as e:
            logger.error(f"[定时任务] 每日数据同步失败: {exchange_name} - {e}")

    async def _quick_sync_job(self):
        """快速增量同步（只同步最近数据，用于盘中更新）"""
        logger.info("[定时任务] 开始快速增量同步")
        try:
            from app.services.data_sync_service import data_sync_service
            # 使用默认交易所，回溯1天确保数据完整
            await data_sync_service.sync_all(
                exchange_name='okx',
                history_days=1,
            )
            logger.info("[定时任务] 快速增量同步完成")
        except Exception as e:
            logger.error(f"[定时任务] 快速增量同步失败: {e}")

    # ============================================
    # 管理接口
    # ============================================

    def get_jobs(self):
        """获取所有定时任务"""
        if not self._scheduler:
            return []

        jobs = []
        for job in self._scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': next_run.strftime('%Y-%m-%d %H:%M:%S') if next_run else None,
                'trigger': str(job.trigger),
            })
        return jobs

    def _log_scheduled_jobs(self):
        """记录已注册的定时任务"""
        for job in self._scheduler.get_jobs():
            next_run = job.next_run_time
            logger.info(
                f"  定时任务: {job.name} "
                f"| 触发器: {job.trigger} "
                f"| 下次执行: {next_run.strftime('%Y-%m-%d %H:%M:%S') if next_run else 'N/A'}"
            )

    @property
    def is_running(self) -> bool:
        return self._running


# 全局实例
scheduler_service = SchedulerService()
