"""
Agent B: Backtester — 回测执行器
不调用 LLM，直接复用 v2 回测引擎
"""
import asyncio
import logging
from typing import Any, Dict, Optional

from app.services.agent.code_sandbox import load_strategy_functions, CodeSafetyError
from app.services.strategy_backtest import Backtest, BacktestConfig, BacktestResultV2
from app.core.config import settings

logger = logging.getLogger(__name__)


def _extract_metrics(result: BacktestResultV2) -> Dict[str, Any]:
    """从 BacktestResultV2 提取关键绩效指标字典"""
    return {
        "initial_capital": result.initial_capital,
        "final_equity": round(result.final_equity, 2),
        "total_return_pct": round(result.total_return_pct, 2),
        "annual_return_pct": round(result.annual_return_pct, 2),
        "max_drawdown_pct": round(result.max_drawdown_pct, 2),
        "max_drawdown_duration_days": result.max_drawdown_duration_days,
        "sharpe_ratio": round(result.sharpe_ratio, 3),
        "sortino_ratio": round(result.sortino_ratio, 3),
        "calmar_ratio": round(result.calmar_ratio, 3),
        "win_rate_pct": round(result.win_rate_pct, 2),
        "profit_factor": round(result.profit_factor, 3),
        "avg_win_pct": round(result.avg_win_pct, 2),
        "avg_loss_pct": round(result.avg_loss_pct, 2),
        "max_consecutive_wins": result.max_consecutive_wins,
        "max_consecutive_losses": result.max_consecutive_losses,
        "total_trades": result.total_trades,
        "winning_trades": result.winning_trades,
        "losing_trades": result.losing_trades,
        "largest_win": round(result.largest_win, 2),
        "largest_loss": round(result.largest_loss, 2),
        "total_fees": round(result.total_fees, 2),
        "avg_holding_bars": round(result.avg_holding_bars, 1),
        "expectancy": round(result.expectancy, 4),
        "total_bars": result.total_bars,
        "elapsed_seconds": round(result.elapsed_seconds, 2),
        "status": result.status,
        "equity_curve_len": len(result.equity_curve),
    }


class BacktesterAgent:
    """
    回测执行 Agent：加载 AI 生成的代码并在 v2 引擎中执行。
    """

    async def run(
        self,
        strategy_code: str,
        setup_code: str,
        symbol: str = "BTC/USDT",
        timeframe: str = "4h",
        start_date: str = "2024-01-01",
        end_date: str = "2025-12-31",
        stop_loss: Optional[float] = None,
        initial_capital: float = 10000.0,
    ) -> Dict[str, Any]:
        """
        执行回测并返回指标字典。

        Returns:
            {"metrics": dict, "trades_count": int, "error": str}
        """
        try:
            strategy_fn, setup_fn = load_strategy_functions(strategy_code, setup_code)
        except CodeSafetyError as e:
            return {"metrics": {}, "trades_count": 0, "error": f"代码安全检查失败: {e}"}
        except Exception as e:
            return {"metrics": {}, "trades_count": 0, "error": f"代码加载失败: {e}"}

        config = BacktestConfig(
            exchange="okx",
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            stop_loss=stop_loss,
        )

        try:
            bt = Backtest(config, strategy_fn, setup_fn)
            result: BacktestResultV2 = await asyncio.to_thread(bt.run)

            if result.status != "completed":
                return {
                    "metrics": _extract_metrics(result),
                    "trades_count": result.total_trades,
                    "error": result.error_message or "回测未正常完成",
                }

            metrics = _extract_metrics(result)
            return {
                "metrics": metrics,
                "trades_count": result.total_trades,
                "error": "",
            }

        except Exception as e:
            logger.exception("Backtester 回测执行异常")
            return {"metrics": {}, "trades_count": 0, "error": f"回测执行异常: {e}"}
