"""
Agent A: Strategist (Generator) — 策略生成师 (v2)

增强:
1. 支持 Sprint 合约 — 先协商再生成
2. 支持 Context Reset — 通过结构化交接文档接收上下文
3. 支持 Pivot/Refine 决策 — 由 Evaluator 驱动方向选择
"""
import json
import logging
from typing import Dict, Any, Optional

from app.services.agent.llm_client import get_qwen_client
from app.services.agent.prompts import (
    STRATEGIST_SYSTEM,
    build_strategist_prompt,
    build_contract_proposal_prompt,
    format_goal_description,
    format_iteration_history,
    format_spec_summary,
)
from app.services.agent.schemas import AgentTask, SprintContract
from app.services.agent.code_sandbox import validate_code, CodeSafetyError

logger = logging.getLogger(__name__)


class StrategistAgent:
    """
    策略生成 Agent: 先提出 Sprint 合约, 再生成代码。
    """

    async def propose_contract(
        self,
        task: AgentTask,
        evaluator_feedback: str = "",
    ) -> Dict[str, Any]:
        """
        提出 Sprint 合约提案。

        Returns:
            {
                "action": "new" | "refine" | "pivot",
                "strategy_direction": str,
                "key_indicators": list,
                "entry_logic_desc": str,
                "exit_logic_desc": str,
                "risk_management_desc": str,
                "acceptance_criteria": list[str],
            }
        """
        client = get_qwen_client()
        goal_desc = format_goal_description(task.goal)
        spec_text = format_spec_summary(task.strategy_spec)
        history_text = format_iteration_history(task.iterations)

        user_prompt = build_contract_proposal_prompt(
            strategy_spec=spec_text,
            goal_desc=goal_desc,
            iteration=len(task.iterations),
            history_summary=history_text,
            evaluator_feedback=evaluator_feedback,
        )

        messages = [
            {"role": "system", "content": STRATEGIST_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]

        try:
            result = await client.chat_json(messages, temperature=0.7, max_tokens=2048)
            action = result.get("action", "new")
            if action not in ("new", "refine", "pivot"):
                action = "new"
            if not task.iterations:
                action = "new"
            result["action"] = action
            logger.info(
                "Strategist 合约提案: %s | 方向: %s",
                action, result.get("strategy_direction", "unknown")[:50],
            )
            return result
        except Exception as e:
            logger.warning("Strategist 合约提案失败: %s", e)
            return {
                "action": "new",
                "strategy_direction": "默认多指标组合策略",
                "key_indicators": ["sma", "rsi", "atr"],
                "entry_logic_desc": "多指标共振信号买入",
                "exit_logic_desc": "趋势反转或止损出场",
                "risk_management_desc": "动态止损 + 仓位控制",
                "acceptance_criteria": ["夏普比率达标", "回撤可控"],
            }

    async def generate(
        self,
        task: AgentTask,
        previous_feedback: str = "",
        contract: Optional[SprintContract] = None,
    ) -> Dict[str, Any]:
        """
        生成或改进策略代码。

        Returns:
            {
                "strategy_name": str,
                "strategy_fn_code": str,
                "setup_fn_code": str,
                "stop_loss": float,
                "timeframe": str,
                "reasoning": str,
            }
        """
        client = get_qwen_client()
        goal_desc = format_goal_description(task.goal)

        contract_text = ""
        if contract:
            contract_text = json.dumps(contract.to_dict(), ensure_ascii=False, indent=2)

        user_prompt = build_strategist_prompt(
            goal_desc=goal_desc,
            symbol=task.symbol,
            timeframe=task.timeframe,
            user_prompt=task.user_prompt,
            previous_feedback=previous_feedback,
            contract=contract_text,
        )

        messages = [
            {"role": "system", "content": STRATEGIST_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]

        max_code_retries = 3
        last_error = ""

        for attempt in range(max_code_retries):
            try:
                if attempt > 0 and last_error:
                    messages.append({
                        "role": "user",
                        "content": (
                            f"上一次生成的代码有问题:\n{last_error}\n"
                            "请修复并重新输出完整 JSON。"
                        ),
                    })

                result = await client.chat_json(messages, temperature=0.7, max_tokens=4096)

                strategy_code = result.get("strategy_fn_code", "")
                setup_code = result.get("setup_fn_code", "def setup(ctx):\n    pass")

                if not strategy_code:
                    last_error = "strategy_fn_code 字段为空"
                    continue

                validate_code(strategy_code, "strategy_fn")
                validate_code(setup_code, "setup_fn")

                logger.info(
                    "Strategist 生成策略: %s (第 %d 次尝试)",
                    result.get("strategy_name", "unknown"),
                    attempt + 1,
                )
                return result

            except CodeSafetyError as e:
                last_error = str(e)
                logger.warning("Strategist 代码安全检查失败 (attempt %d): %s", attempt + 1, e)
            except Exception as e:
                last_error = str(e)
                logger.warning("Strategist 生成失败 (attempt %d): %s", attempt + 1, e)

        raise RuntimeError(f"Strategist 在 {max_code_retries} 次尝试后仍无法生成安全的策略代码: {last_error}")
