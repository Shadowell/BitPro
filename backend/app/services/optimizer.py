"""
策略参数优化框架
================
支持:
  1. 网格搜索 (Grid Search) — 遍历所有参数组合
  2. Walk-Forward 优化 — 滚动窗口训练+验证，防止过拟合
  3. 多币种批量验证 — 检验策略普适性
  4. 排序打分 — 综合 Sharpe/Calmar/收益/回撤 多维度评分
"""
import itertools
import logging
import numpy as np
from typing import Dict, List, Callable, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from concurrent.futures import ProcessPoolExecutor

from app.services.strategy_backtest import (
    Backtest, BacktestConfig, BacktestResultV2, StrategyContext,
)

logger = logging.getLogger(__name__)


# ============================================
# 优化结果
# ============================================

@dataclass
class OptimizationResult:
    """单组参数的优化结果"""
    params: Dict[str, Any]
    result: BacktestResultV2
    score: float = 0.0

    def summary_dict(self) -> Dict:
        r = self.result
        return {
            **self.params,
            'score': round(self.score, 4),
            'return_pct': round(r.total_return_pct, 2),
            'annual_pct': round(r.annual_return_pct, 2),
            'max_dd_pct': round(r.max_drawdown_pct, 2),
            'sharpe': round(r.sharpe_ratio, 3),
            'sortino': round(r.sortino_ratio, 3),
            'calmar': round(r.calmar_ratio, 3),
            'trades': r.total_trades,
            'win_rate': round(r.win_rate_pct, 1),
            'profit_factor': round(r.profit_factor, 2),
            'expectancy': round(r.expectancy, 2),
        }


@dataclass
class WalkForwardWindow:
    """Walk-Forward 单窗口结果"""
    window_index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    best_params: Dict[str, Any]
    train_result: BacktestResultV2
    test_result: BacktestResultV2
    train_score: float = 0.0
    test_score: float = 0.0


@dataclass
class WalkForwardResult:
    """Walk-Forward 总结果"""
    windows: List[WalkForwardWindow] = field(default_factory=list)
    combined_test_return: float = 0.0
    combined_test_sharpe: float = 0.0
    avg_test_return: float = 0.0
    avg_test_sharpe: float = 0.0
    avg_test_max_dd: float = 0.0
    consistency_ratio: float = 0.0  # 盈利窗口比例
    overfitting_ratio: float = 0.0  # 过拟合比率 (train vs test 差异)


# ============================================
# 评分函数
# ============================================

def default_score(result: BacktestResultV2) -> float:
    """
    默认综合评分:
    重点奖励 高夏普 + 低回撤 + 正收益，惩罚过少交易和极端回撤
    """
    if result.status != 'completed' or result.total_trades < 3:
        return -999.0

    sharpe = result.sharpe_ratio
    calmar = result.calmar_ratio
    ret = result.total_return_pct
    dd = result.max_drawdown_pct
    win_rate = result.win_rate_pct
    pf = result.profit_factor

    # 回撤过大直接惩罚
    if dd > 40:
        return -100.0

    # 综合评分公式:
    # 40% 夏普 + 20% Calmar + 20% 收益率(归一化) + 10% 胜率 + 10% 盈亏比
    score = (
        0.40 * sharpe
        + 0.20 * calmar
        + 0.20 * (ret / 100.0)  # 归一化
        + 0.10 * (win_rate / 100.0)
        + 0.10 * min(pf, 3.0) / 3.0  # 盈亏比上限3
    )

    # 交易次数奖励 (太少不好，太多也不好)
    trades = result.total_trades
    if trades < 5:
        score *= 0.5
    elif trades < 10:
        score *= 0.8

    return score


# ============================================
# 网格搜索优化器
# ============================================

class GridOptimizer:
    """
    网格搜索参数优化

    用法:
        optimizer = GridOptimizer(
            strategy_fn=my_strategy,
            base_config=BacktestConfig(...),
            param_grid={
                'bb_period': [15, 20, 25, 30],
                'bb_std': [1.5, 2.0, 2.5],
                'stop_loss': [0.05, 0.08, 0.10],
            },
            score_fn=default_score,
        )
        results = optimizer.run()
    """

    def __init__(
        self,
        strategy_factory: Callable[[Dict[str, Any]], Callable],
        base_config: BacktestConfig,
        param_grid: Dict[str, List[Any]],
        setup_indicators_factory: Callable[[Dict[str, Any]], Callable] = None,
        score_fn: Callable[[BacktestResultV2], float] = None,
    ):
        """
        Args:
            strategy_factory: 接收参数字典，返回策略函数
            base_config: 基础回测配置
            param_grid: 参数搜索空间
            setup_indicators_factory: 可选，接收参数字典，返回指标初始化函数
            score_fn: 评分函数
        """
        self.strategy_factory = strategy_factory
        self.base_config = base_config
        self.param_grid = param_grid
        self.setup_indicators_factory = setup_indicators_factory
        self.score_fn = score_fn or default_score

    def run(self, top_n: int = 10) -> List[OptimizationResult]:
        """
        运行网格搜索

        Returns:
            按评分排序的结果列表
        """
        # 生成所有参数组合
        param_names = list(self.param_grid.keys())
        param_values = list(self.param_grid.values())
        combinations = list(itertools.product(*param_values))

        total = len(combinations)
        logger.info(f"网格搜索: {total} 个参数组合")
        print(f"\n网格搜索: {total} 个参数组合...")

        results = []

        for idx, combo in enumerate(combinations):
            params = dict(zip(param_names, combo))

            # 应用参数到配置
            config = self._apply_params(params)

            # 创建策略
            strategy_fn = self.strategy_factory(params)
            setup_fn = self.setup_indicators_factory(params) if self.setup_indicators_factory else None

            # 运行回测
            bt = Backtest(config, strategy_fn, setup_fn)
            result = bt.run()

            # 评分
            score = self.score_fn(result)

            opt_result = OptimizationResult(
                params=params,
                result=result,
                score=score,
            )
            results.append(opt_result)

            if (idx + 1) % 20 == 0 or idx == total - 1:
                print(f"  进度: {idx+1}/{total} ({(idx+1)/total*100:.0f}%)")

        # 排序
        results.sort(key=lambda x: x.score, reverse=True)

        # 打印 Top N
        print(f"\n{'='*90}")
        print(f"  网格搜索结果 Top {min(top_n, len(results))}")
        print(f"{'='*90}")

        header = f"{'#':>3} {'Score':>7}"
        for p in param_names:
            header += f" {p:>10}"
        header += f" {'Return%':>8} {'Annual%':>8} {'MaxDD%':>7} {'Sharpe':>7} {'Trades':>6} {'WinR%':>6}"
        print(header)
        print('─' * 90)

        for i, r in enumerate(results[:top_n]):
            line = f"{i+1:>3} {r.score:>7.3f}"
            for p in param_names:
                val = r.params[p]
                if val is None:
                    line += f" {'None':>10}"
                elif isinstance(val, float):
                    line += f" {val:>10.4f}"
                else:
                    line += f" {val:>10}"
            line += (
                f" {r.result.total_return_pct:>+8.2f}"
                f" {r.result.annual_return_pct:>+8.2f}"
                f" {r.result.max_drawdown_pct:>7.1f}"
                f" {r.result.sharpe_ratio:>7.3f}"
                f" {r.result.total_trades:>6}"
                f" {r.result.win_rate_pct:>6.1f}"
            )
            print(line)

        return results

    def _apply_params(self, params: Dict[str, Any]) -> BacktestConfig:
        """将参数应用到配置"""
        config = BacktestConfig(
            exchange=self.base_config.exchange,
            symbol=self.base_config.symbol,
            timeframe=self.base_config.timeframe,
            start_date=self.base_config.start_date,
            end_date=self.base_config.end_date,
            initial_capital=self.base_config.initial_capital,
            commission=self.base_config.commission,
            slippage=self.base_config.slippage,
            allow_short=self.base_config.allow_short,
            max_leverage=self.base_config.max_leverage,
            stop_loss=params.get('stop_loss', self.base_config.stop_loss),
            take_profit=params.get('take_profit', self.base_config.take_profit),
            trailing_stop=params.get('trailing_stop', self.base_config.trailing_stop),
            indicators_config=params,
        )
        return config


# ============================================
# Walk-Forward 优化器
# ============================================

class WalkForwardOptimizer:
    """
    Walk-Forward 滚动优化

    将数据分成多个 [训练期 + 测试期] 窗口：
    - 在训练期用网格搜索找最优参数
    - 用最优参数在测试期验证
    - 滚动到下一个窗口

    这是检验策略是否过拟合的金标准方法。
    """

    def __init__(
        self,
        strategy_factory: Callable[[Dict[str, Any]], Callable],
        base_config: BacktestConfig,
        param_grid: Dict[str, List[Any]],
        setup_indicators_factory: Callable[[Dict[str, Any]], Callable] = None,
        score_fn: Callable[[BacktestResultV2], float] = None,
        train_days: int = 270,     # 训练窗口天数 (~9个月)
        test_days: int = 90,       # 测试窗口天数 (~3个月)
        step_days: int = 90,       # 滚动步长
    ):
        self.strategy_factory = strategy_factory
        self.base_config = base_config
        self.param_grid = param_grid
        self.setup_indicators_factory = setup_indicators_factory
        self.score_fn = score_fn or default_score
        self.train_days = train_days
        self.test_days = test_days
        self.step_days = step_days

    def run(self) -> WalkForwardResult:
        """运行 Walk-Forward 优化"""
        start = datetime.strptime(self.base_config.start_date, "%Y-%m-%d")
        end = datetime.strptime(self.base_config.end_date, "%Y-%m-%d")

        wf_result = WalkForwardResult()
        window_idx = 0

        print(f"\n{'='*70}")
        print(f"  Walk-Forward 优化")
        print(f"  训练窗口: {self.train_days}天 | 测试窗口: {self.test_days}天 | 步长: {self.step_days}天")
        print(f"{'='*70}")

        current = start
        while current + timedelta(days=self.train_days + self.test_days) <= end:
            train_start = current.strftime("%Y-%m-%d")
            train_end = (current + timedelta(days=self.train_days)).strftime("%Y-%m-%d")
            test_start = train_end
            test_end = (current + timedelta(days=self.train_days + self.test_days)).strftime("%Y-%m-%d")

            print(f"\n  窗口 {window_idx+1}: 训练 {train_start}~{train_end} | 测试 {test_start}~{test_end}")

            # 1. 在训练期网格搜索
            train_config = BacktestConfig(
                exchange=self.base_config.exchange,
                symbol=self.base_config.symbol,
                timeframe=self.base_config.timeframe,
                start_date=train_start,
                end_date=train_end,
                initial_capital=self.base_config.initial_capital,
                commission=self.base_config.commission,
                slippage=self.base_config.slippage,
                allow_short=self.base_config.allow_short,
                max_leverage=self.base_config.max_leverage,
            )

            grid = GridOptimizer(
                strategy_factory=self.strategy_factory,
                base_config=train_config,
                param_grid=self.param_grid,
                setup_indicators_factory=self.setup_indicators_factory,
                score_fn=self.score_fn,
            )

            # 静默模式运行训练
            import io, sys
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            train_results = grid.run(top_n=1)
            sys.stdout = old_stdout

            if not train_results or train_results[0].score <= -900:
                print(f"    训练期无有效结果，跳过")
                current += timedelta(days=self.step_days)
                window_idx += 1
                continue

            best = train_results[0]
            best_params = best.params

            print(f"    最优参数: {best_params}")
            print(f"    训练期: 收益 {best.result.total_return_pct:+.2f}% | Sharpe {best.result.sharpe_ratio:.2f}")

            # 2. 在测试期验证
            test_config = BacktestConfig(
                exchange=self.base_config.exchange,
                symbol=self.base_config.symbol,
                timeframe=self.base_config.timeframe,
                start_date=test_start,
                end_date=test_end,
                initial_capital=self.base_config.initial_capital,
                commission=self.base_config.commission,
                slippage=self.base_config.slippage,
                allow_short=self.base_config.allow_short,
                max_leverage=self.base_config.max_leverage,
                stop_loss=best_params.get('stop_loss'),
                take_profit=best_params.get('take_profit'),
                trailing_stop=best_params.get('trailing_stop'),
                indicators_config=best_params,
            )

            strategy_fn = self.strategy_factory(best_params)
            setup_fn = self.setup_indicators_factory(best_params) if self.setup_indicators_factory else None
            test_result = Backtest(test_config, strategy_fn, setup_fn).run()
            test_score = self.score_fn(test_result)

            print(f"    测试期: 收益 {test_result.total_return_pct:+.2f}% | Sharpe {test_result.sharpe_ratio:.2f}")

            wf_window = WalkForwardWindow(
                window_index=window_idx,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                best_params=best_params,
                train_result=best.result,
                test_result=test_result,
                train_score=best.score,
                test_score=test_score,
            )
            wf_result.windows.append(wf_window)

            current += timedelta(days=self.step_days)
            window_idx += 1

        # 汇总 Walk-Forward 结果
        self._summarize(wf_result)
        return wf_result

    def _summarize(self, wf: WalkForwardResult):
        """汇总 Walk-Forward 结果"""
        if not wf.windows:
            print("\n  无有效窗口结果")
            return

        test_returns = [w.test_result.total_return_pct for w in wf.windows]
        test_sharpes = [w.test_result.sharpe_ratio for w in wf.windows]
        test_dds = [w.test_result.max_drawdown_pct for w in wf.windows]
        train_returns = [w.train_result.total_return_pct for w in wf.windows]

        wf.avg_test_return = np.mean(test_returns)
        wf.avg_test_sharpe = np.mean(test_sharpes)
        wf.avg_test_max_dd = np.mean(test_dds)

        # 复合收益
        compound = 1.0
        for r in test_returns:
            compound *= (1 + r / 100.0)
        wf.combined_test_return = (compound - 1) * 100

        # 一致性比率: 盈利窗口 / 总窗口
        profitable = sum(1 for r in test_returns if r > 0)
        wf.consistency_ratio = profitable / len(test_returns) if test_returns else 0

        # 过拟合比率
        if train_returns and test_returns:
            avg_train = np.mean(train_returns)
            avg_test = np.mean(test_returns)
            if abs(avg_train) > 0:
                wf.overfitting_ratio = 1 - (avg_test / avg_train) if avg_train > 0 else 0

        print(f"\n{'='*70}")
        print(f"  Walk-Forward 汇总 ({len(wf.windows)} 个窗口)")
        print(f"{'='*70}")
        print(f"  复合测试收益:     {wf.combined_test_return:+.2f}%")
        print(f"  平均测试收益:     {wf.avg_test_return:+.2f}%")
        print(f"  平均测试夏普:     {wf.avg_test_sharpe:.3f}")
        print(f"  平均测试回撤:     {wf.avg_test_max_dd:.1f}%")
        print(f"  一致性比率:       {wf.consistency_ratio:.0%} (盈利窗口占比)")
        print(f"  过拟合比率:       {wf.overfitting_ratio:.0%} (越低越好, <50%为合格)")
        print(f"{'='*70}")

        print(f"\n  窗口明细:")
        print(f"  {'#':>3} {'训练收益%':>10} {'测试收益%':>10} {'测试Sharpe':>11} {'测试MaxDD%':>11}")
        print(f"  {'─'*50}")
        for w in wf.windows:
            print(
                f"  {w.window_index+1:>3}"
                f" {w.train_result.total_return_pct:>+10.2f}"
                f" {w.test_result.total_return_pct:>+10.2f}"
                f" {w.test_result.sharpe_ratio:>11.3f}"
                f" {w.test_result.max_drawdown_pct:>11.1f}"
            )


# ============================================
# 多币种验证
# ============================================

def multi_symbol_test(
    strategy_factory: Callable,
    params: Dict[str, Any],
    symbols: List[str],
    base_config: BacktestConfig,
    setup_indicators_factory: Callable = None,
) -> Dict[str, BacktestResultV2]:
    """
    多币种回测验证

    用同一套参数在多个币种上回测，检验策略普适性。
    """
    print(f"\n{'='*70}")
    print(f"  多币种验证 ({len(symbols)} 个币种)")
    print(f"  参数: {params}")
    print(f"{'='*70}")

    results = {}
    strategy_fn = strategy_factory(params)
    setup_fn = setup_indicators_factory(params) if setup_indicators_factory else None

    header = f"  {'币种':<12} {'收益%':>8} {'年化%':>8} {'MaxDD%':>7} {'Sharpe':>7} {'Sortino':>8} {'Calmar':>7} {'交易':>5} {'胜率%':>6}"
    print(header)
    print(f"  {'─'*70}")

    for symbol in symbols:
        config = BacktestConfig(
            exchange=base_config.exchange,
            symbol=symbol,
            timeframe=base_config.timeframe,
            start_date=base_config.start_date,
            end_date=base_config.end_date,
            initial_capital=base_config.initial_capital,
            commission=base_config.commission,
            slippage=base_config.slippage,
            allow_short=base_config.allow_short,
            max_leverage=base_config.max_leverage,
            stop_loss=params.get('stop_loss'),
            take_profit=params.get('take_profit'),
            trailing_stop=params.get('trailing_stop'),
            indicators_config=params,
        )

        result = Backtest(config, strategy_fn, setup_fn).run()
        results[symbol] = result

        print(
            f"  {symbol:<12}"
            f" {result.total_return_pct:>+8.2f}"
            f" {result.annual_return_pct:>+8.2f}"
            f" {result.max_drawdown_pct:>7.1f}"
            f" {result.sharpe_ratio:>7.3f}"
            f" {result.sortino_ratio:>8.3f}"
            f" {result.calmar_ratio:>7.3f}"
            f" {result.total_trades:>5}"
            f" {result.win_rate_pct:>6.1f}"
        )

    # 汇总
    avg_ret = np.mean([r.total_return_pct for r in results.values()])
    avg_sharpe = np.mean([r.sharpe_ratio for r in results.values()])
    avg_dd = np.mean([r.max_drawdown_pct for r in results.values()])
    profitable = sum(1 for r in results.values() if r.total_return_pct > 0)

    print(f"  {'─'*70}")
    print(f"  {'平均':<12} {avg_ret:>+8.2f} {'':>8} {avg_dd:>7.1f} {avg_sharpe:>7.3f}")
    print(f"  盈利币种: {profitable}/{len(symbols)}")

    return results
