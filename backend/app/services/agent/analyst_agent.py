"""
Agent C: Analyst — 已废弃, 功能迁移至 EvaluatorAgent

保留此模块仅为向后兼容, 内部代理到 EvaluatorAgent。
"""
import logging
from typing import Any, Dict

from app.services.agent.evaluator_agent import EvaluatorAgent
from app.services.agent.schemas import AgentTask

logger = logging.getLogger(__name__)


class AnalystAgent:
    """向后兼容包装器, 内部使用 EvaluatorAgent。"""

    def __init__(self):
        self._evaluator = EvaluatorAgent()

    async def analyze(
        self,
        task: AgentTask,
        strategy_code: str,
        setup_code: str,
        metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        logger.warning("AnalystAgent 已废弃, 请使用 EvaluatorAgent")
        result = await self._evaluator.evaluate(
            task=task,
            strategy_code=strategy_code,
            setup_code=setup_code,
            metrics=metrics,
        )
        return {
            "meets_goal": result["meets_goal"],
            "score": result["score"],
            "analysis": result["analysis"],
            "issues": result.get("issues", []),
            "suggestions": result.get("suggestions", []),
            "parameter_hints": {},
        }
