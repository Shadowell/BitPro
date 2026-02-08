"""
策略管理服务
"""
from typing import List, Dict, Optional
from datetime import datetime
import json
import logging

from app.db.local_db import db_instance as db
from app.models.schemas import StrategyCreate, StrategyUpdate
from app.services.strategy_engine import strategy_engine

logger = logging.getLogger(__name__)


class StrategyService:
    """策略管理服务"""
    
    async def get_strategies(self) -> List[Dict]:
        """获取所有策略"""
        strategies = db.get_strategies()
        return strategies
    
    async def get_strategy(self, strategy_id: int) -> Optional[Dict]:
        """获取策略详情"""
        return db.get_strategy_by_id(strategy_id)
    
    async def create_strategy(self, strategy: StrategyCreate) -> Dict:
        """创建策略"""
        strategy_id = db.save_strategy(
            name=strategy.name,
            script_content=strategy.script_content,
            description=strategy.description,
            config=strategy.config,
            exchange=strategy.exchange,
            symbols=strategy.symbols
        )
        
        return await self.get_strategy(strategy_id)
    
    async def update_strategy(self, strategy_id: int, strategy: StrategyUpdate) -> Optional[Dict]:
        """更新策略"""
        existing = db.get_strategy_by_id(strategy_id)
        if not existing:
            return None
        
        # 检查策略是否在运行
        status = strategy_engine.get_strategy_status(strategy_id)
        if status and status.get('status') == 'running':
            raise ValueError("Cannot update running strategy")
        
        # 合并更新
        update_data = {
            'name': strategy.name or existing['name'],
            'script_content': strategy.script_content or existing['script_content'],
            'description': strategy.description if strategy.description is not None else existing.get('description'),
            'config': strategy.config if strategy.config is not None else existing.get('config'),
            'exchange': strategy.exchange if strategy.exchange is not None else existing.get('exchange'),
            'symbols': strategy.symbols if strategy.symbols is not None else existing.get('symbols'),
        }
        
        db.save_strategy(**update_data)
        
        return await self.get_strategy(strategy_id)
    
    async def delete_strategy(self, strategy_id: int) -> bool:
        """删除策略"""
        # 如果策略正在运行，先停止
        await self.stop_strategy(strategy_id)
        return db.delete_strategy(strategy_id)
    
    async def start_strategy(self, strategy_id: int) -> bool:
        """启动策略"""
        return await strategy_engine.start_strategy(strategy_id)
    
    async def stop_strategy(self, strategy_id: int) -> bool:
        """停止策略"""
        return await strategy_engine.stop_strategy(strategy_id)
    
    async def get_strategy_trades(self, strategy_id: int, limit: int = 50) -> List[Dict]:
        """获取策略交易记录"""
        return db.get_strategy_trades(strategy_id, limit)
    
    async def get_strategy_status(self, strategy_id: int) -> Optional[Dict]:
        """获取策略运行状态"""
        # 先从引擎获取实时状态
        engine_status = strategy_engine.get_strategy_status(strategy_id)
        if engine_status:
            return engine_status
        
        # 否则从数据库获取
        strategy = db.get_strategy_by_id(strategy_id)
        if not strategy:
            return None
        
        # 获取最近交易
        recent_trades = db.get_strategy_trades(strategy_id, 5)
        
        # 计算 PnL
        total_pnl = sum(t.get('pnl', 0) or 0 for t in recent_trades)
        
        return {
            'strategy_id': strategy_id,
            'name': strategy['name'],
            'status': strategy.get('status', 'stopped'),
            'exchange': strategy.get('exchange'),
            'symbols': strategy.get('symbols'),
            'pnl': total_pnl,
            'total_trades': len(recent_trades),
            'positions': {},
            'error_message': None,
            'started_at': None,
        }
    
    async def get_all_running(self) -> List[Dict]:
        """获取所有运行中的策略"""
        return strategy_engine.get_all_running()


# 全局服务实例
strategy_service = StrategyService()
