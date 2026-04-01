"""
Agent 系统 API 端点 (v2)
Multi-Agent 量化策略协同系统
"""
import asyncio
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.db.local_db import db_instance as db
from app.services.agent.schemas import (
    AgentTask, GoalCriteria, IterationRecord,
    CreateTaskRequest, TaskStatusResponse, IterationResponse,
)
from app.services.agent.orchestrator import orchestrator

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================
# 持久化回调
# ============================================

async def _persist_iteration(task: AgentTask, record: IterationRecord):
    try:
        db.save_agent_task({
            "id": task.task_id,
            "status": task.status,
            "goal_criteria": task.goal.to_dict(),
            "symbol": task.symbol,
            "timeframe": task.timeframe,
            "backtest_start": task.backtest_start,
            "backtest_end": task.backtest_end,
            "max_iterations": task.max_iterations,
            "current_iteration": task.current_iteration,
            "best_iteration": task.best_iteration,
            "user_prompt": task.user_prompt,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        })
        db.save_agent_iteration(task.task_id, record.to_dict())
    except Exception as e:
        logger.warning("Agent 持久化失败: %s", e)


orchestrator.set_on_iteration(_persist_iteration)


# ============================================
# 后台任务执行
# ============================================

async def _run_task_background(task_id: str):
    try:
        task = await orchestrator.run_task(task_id)
        db.save_agent_task({
            "id": task.task_id,
            "status": task.status,
            "goal_criteria": task.goal.to_dict(),
            "symbol": task.symbol,
            "timeframe": task.timeframe,
            "backtest_start": task.backtest_start,
            "backtest_end": task.backtest_end,
            "max_iterations": task.max_iterations,
            "current_iteration": task.current_iteration,
            "best_iteration": task.best_iteration,
            "user_prompt": task.user_prompt,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        })
        logger.info("Agent 任务 %s 已完成, 状态: %s", task_id, task.status)
    except Exception as e:
        logger.exception("Agent 任务 %s 执行失败", task_id)
        task = orchestrator.get_task(task_id)
        if task:
            task.status = "failed"
            db.save_agent_task({
                "id": task.task_id,
                "status": "failed",
                "goal_criteria": task.goal.to_dict(),
                "symbol": task.symbol,
                "timeframe": task.timeframe,
                "backtest_start": task.backtest_start,
                "backtest_end": task.backtest_end,
                "max_iterations": task.max_iterations,
                "current_iteration": task.current_iteration,
                "best_iteration": task.best_iteration,
                "user_prompt": task.user_prompt,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
            })


# ============================================
# API 端点
# ============================================

@router.post("/tasks", summary="创建 Agent 任务")
async def create_task(req: CreateTaskRequest):
    from app.core.config import settings
    if not settings.QWEN_API_KEY:
        raise HTTPException(400, "QWEN_API_KEY 未配置，请在 .env 中设置")

    task = orchestrator.create_task(req)

    db.save_agent_task({
        "id": task.task_id,
        "status": task.status,
        "goal_criteria": task.goal.to_dict(),
        "symbol": task.symbol,
        "timeframe": task.timeframe,
        "backtest_start": task.backtest_start,
        "backtest_end": task.backtest_end,
        "max_iterations": task.max_iterations,
        "current_iteration": 0,
        "best_iteration": None,
        "user_prompt": task.user_prompt,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    })

    asyncio.create_task(_run_task_background(task.task_id))

    return {
        "task_id": task.task_id,
        "status": task.status,
        "message": f"任务已创建并启动 (v2 多Agent架构)，最多迭代 {task.max_iterations} 轮",
    }


@router.get("/tasks", summary="列出所有 Agent 任务")
async def list_tasks():
    in_memory = orchestrator.list_tasks()
    if in_memory:
        return [_task_to_status(t) for t in in_memory]
    db_tasks = db.get_agent_tasks(limit=50)
    return db_tasks


@router.get("/tasks/{task_id}", summary="查询任务状态")
async def get_task(task_id: str):
    task = orchestrator.get_task(task_id)
    if task:
        return _task_to_status(task)
    db_task = db.get_agent_task(task_id)
    if not db_task:
        raise HTTPException(404, f"任务 {task_id} 不存在")
    return db_task


@router.get("/tasks/{task_id}/iterations", summary="查看迭代记录")
async def get_iterations(task_id: str):
    task = orchestrator.get_task(task_id)
    if task:
        return [rec.to_dict() for rec in task.iterations]
    db_iterations = db.get_agent_iterations(task_id)
    if not db_iterations:
        db_task = db.get_agent_task(task_id)
        if not db_task:
            raise HTTPException(404, f"任务 {task_id} 不存在")
    return db_iterations


@router.post("/tasks/{task_id}/stop", summary="停止任务")
async def stop_task(task_id: str):
    if orchestrator.stop_task(task_id):
        return {"message": f"任务 {task_id} 已停止"}
    raise HTTPException(400, f"任务 {task_id} 不在运行中或不存在")


@router.post("/tasks/{task_id}/accept", summary="接受最佳策略")
async def accept_best_strategy(task_id: str):
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(404, f"任务 {task_id} 不存在")

    best = task.best_record
    if not best or not best.strategy_code:
        raise HTTPException(400, "没有可接受的策略 (无有效迭代记录)")

    scores_text = ""
    if best.eval_scores:
        s = best.eval_scores
        scores_text = (
            f"\n维度评分: 风控={s.risk_control:.0f} 盈利={s.profitability:.0f} "
            f"稳健={s.robustness:.0f} 逻辑={s.strategy_logic:.0f} 原创={s.originality:.0f}"
        )

    strategy_id = db.save_strategy(
        name=f"[AI] {best.strategy_name}",
        description=(
            f"由 AI Agent v2 系统自动生成 (任务 {task_id}, 第 {best.iteration + 1} 轮)\n"
            f"综合评分: {best.score:.0f}/100{scores_text}\n"
            f"设计思路: {best.reasoning}"
        ),
        script_content=best.strategy_code,
        config=json.dumps({
            "agent_task_id": task_id,
            "agent_iteration": best.iteration,
            "setup_code": best.setup_code,
            "backtest_metrics": best.backtest_metrics,
            "eval_scores": best.eval_scores.to_dict() if best.eval_scores else None,
        }),
        exchange="okx",
        symbols=json.dumps([task.symbol]),
    )

    return {
        "message": "策略已保存到数据库",
        "strategy_id": strategy_id,
        "strategy_name": f"[AI] {best.strategy_name}",
    }


def _task_to_status(task: AgentTask) -> dict:
    best_score = None
    best_metrics = None
    best_eval_scores = None
    if task.best_record:
        best_score = task.best_record.score
        best_metrics = task.best_record.backtest_metrics
        if task.best_record.eval_scores:
            best_eval_scores = task.best_record.eval_scores.to_dict()

    return {
        "task_id": task.task_id,
        "status": task.status,
        "symbol": task.symbol,
        "timeframe": task.timeframe,
        "current_iteration": task.current_iteration,
        "max_iterations": task.max_iterations,
        "best_iteration": task.best_iteration,
        "best_score": best_score,
        "best_metrics": best_metrics,
        "best_eval_scores": best_eval_scores,
        "goal": task.goal.to_dict(),
        "user_prompt": task.user_prompt,
        "strategy_spec": task.strategy_spec.to_dict() if task.strategy_spec else None,
        "iterations_count": len(task.iterations),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }
