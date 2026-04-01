"""
Evaluator Agent — 独立策略评估者 (v2)

借鉴 Anthropic 文章核心设计:
1. 评估者独立于生成者 — 分离消除了自我评估偏见
2. 多维度量化评分 — 将主观判断转化为具体可打分的标准
3. 合约验收 — 对照 Sprint 合约逐条检查
4. Pivot/Refine 决策 — 根据趋势判断下一步方向
"""
import json
import logging
from typing import Any, Dict, List, Optional

from app.services.agent.llm_client import get_qwen_client
from app.services.agent.prompts import (
    EVALUATOR_SYSTEM,
    CONTRACT_NEGOTIATION_SYSTEM,
    build_evaluator_prompt,
    build_contract_review_prompt,
    format_goal_description,
    format_iteration_history,
)
from app.services.agent.schemas import (
    AgentTask, EvalScores, SprintContract, IterationRecord,
)

logger = logging.getLogger(__name__)


class EvaluatorAgent:
    """
    独立评估 Agent: 多维度打分 + 合约验收 + 方向决策。
    关键区别于旧 Analyst: 这是一个 skeptical evaluator, 而非策略的 co-creator。
    """

    async def evaluate(
        self,
        task: AgentTask,
        strategy_code: str,
        setup_code: str,
        metrics: Dict[str, Any],
        contract: Optional[SprintContract] = None,
    ) -> Dict[str, Any]:
        """
        评估策略并返回多维度评分和建议。

        Returns:
            {
                "eval_scores": EvalScores,
                "meets_goal": bool,
                "score": float,          # 加权综合分
                "analysis": str,
                "issues": list[str],
                "suggestions": list[str],
                "contract_verdict": list[str],
                "next_action": "refine" | "pivot",
            }
        """
        client = get_qwen_client()
        goal_desc = format_goal_description(task.goal)
        history_text = format_iteration_history(task.iterations)

        contract_text = ""
        if contract:
            contract_text = json.dumps(contract.to_dict(), ensure_ascii=False, indent=2)

        user_prompt = build_evaluator_prompt(
            goal_desc=goal_desc,
            strategy_code=strategy_code,
            setup_code=setup_code,
            metrics=metrics,
            contract=contract_text,
            iteration_history=history_text,
        )

        messages = [
            {"role": "system", "content": EVALUATOR_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]

        try:
            result = await client.chat_json(messages, temperature=0.3, max_tokens=4096)

            eval_scores = EvalScores(
                risk_control=self._safe_score(result.get("risk_control", 50)),
                profitability=self._safe_score(result.get("profitability", 50)),
                robustness=self._safe_score(result.get("robustness", 50)),
                strategy_logic=self._safe_score(result.get("strategy_logic", 50)),
                originality=self._safe_score(result.get("originality", 30)),
            )

            meets_goal_llm = result.get("meets_goal", False)
            meets_goal_hard = task.goal.check(metrics)
            meets_goal = meets_goal_llm and meets_goal_hard

            total_score = eval_scores.total_score

            next_action = result.get("next_action", "refine")
            if next_action not in ("refine", "pivot"):
                next_action = "refine"

            logger.info(
                "Evaluator 评分: 风控=%.0f 盈利=%.0f 稳健=%.0f 逻辑=%.0f 原创=%.0f → 综合=%.1f | 达标=%s | 下一步=%s",
                eval_scores.risk_control, eval_scores.profitability,
                eval_scores.robustness, eval_scores.strategy_logic,
                eval_scores.originality, total_score, meets_goal, next_action,
            )

            return {
                "eval_scores": eval_scores,
                "meets_goal": meets_goal,
                "score": total_score,
                "analysis": result.get("analysis", ""),
                "issues": result.get("issues", []),
                "suggestions": result.get("suggestions", []),
                "contract_verdict": result.get("contract_verdict", []),
                "next_action": next_action,
            }

        except Exception as e:
            logger.exception("Evaluator 评估失败")
            hard_check = task.goal.check(metrics)
            return {
                "eval_scores": EvalScores(
                    risk_control=50, profitability=50, robustness=50,
                    strategy_logic=50, originality=30,
                ),
                "meets_goal": hard_check,
                "score": 46.0 if hard_check else 25.0,
                "analysis": f"LLM 评估失败 ({e})，仅使用硬性指标判断",
                "issues": ["LLM 评估不可用"],
                "suggestions": ["请检查 QWEN_API_KEY 配置"],
                "contract_verdict": [],
                "next_action": "refine",
            }

    async def review_contract(
        self,
        contract_proposal: Dict[str, Any],
        task: AgentTask,
    ) -> Dict[str, Any]:
        """
        审查 Strategist 提出的 Sprint 合约提案。

        Returns:
            {
                "verdict": "approved" | "revision_needed",
                "added_criteria": list[str],
                "feedback": str,
            }
        """
        client = get_qwen_client()
        goal_desc = format_goal_description(task.goal)
        proposal_text = json.dumps(contract_proposal, ensure_ascii=False, indent=2)

        user_prompt = build_contract_review_prompt(
            contract_proposal=proposal_text,
            goal_desc=goal_desc,
        )

        messages = [
            {"role": "system", "content": CONTRACT_NEGOTIATION_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]

        try:
            result = await client.chat_json(messages, temperature=0.3, max_tokens=2048)
            logger.info("Evaluator 合约审查: %s", result.get("verdict", "unknown"))
            return {
                "verdict": result.get("verdict", "approved"),
                "added_criteria": result.get("added_criteria", []),
                "feedback": result.get("feedback", ""),
            }
        except Exception as e:
            logger.warning("Evaluator 合约审查失败: %s", e)
            return {
                "verdict": "approved",
                "added_criteria": [],
                "feedback": f"审查失败 ({e})，默认接受",
            }

    @staticmethod
    def _safe_score(v) -> float:
        try:
            s = float(v)
            return max(0.0, min(100.0, s))
        except (TypeError, ValueError):
            return 50.0
