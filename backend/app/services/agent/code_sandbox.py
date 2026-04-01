"""
策略代码安全沙箱
AST 静态分析 + 动态加载 + 执行隔离
"""
import ast
import logging
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

FORBIDDEN_MODULES = frozenset({
    "os", "sys", "subprocess", "shutil", "pathlib",
    "socket", "http", "urllib", "requests", "httpx", "aiohttp",
    "ctypes", "importlib", "builtins", "code", "codeop",
    "pickle", "shelve", "marshal", "signal", "multiprocessing",
    "threading", "asyncio", "io", "tempfile", "glob",
})

FORBIDDEN_NAMES = frozenset({
    "eval", "exec", "compile", "__import__", "open",
    "globals", "locals", "getattr", "setattr", "delattr",
    "breakpoint", "exit", "quit",
})

ALLOWED_IMPORTS = {
    "numpy": {"np"},
    "math": {"math"},
}

ALLOWED_FROM_IMPORTS = {
    "app.services.indicators": {
        "SMA", "EMA", "RSI", "MACD", "BBANDS", "ATR", "KDJ", "OBV",
        "CROSS_ABOVE", "CROSS_BELOW", "HIGHEST", "LOWEST",
        "STOCH_RSI", "VOLATILITY", "VWAP", "WMA", "PERCENT_RANK",
    },
    "app.services.strategy_backtest": {
        "SMA", "EMA", "RSI", "MACD", "BBANDS", "ATR",
    },
}


class CodeSafetyError(Exception):
    """代码安全检查未通过"""


class _SafetyVisitor(ast.NodeVisitor):
    """AST 遍历器，检查危险节点"""

    def __init__(self):
        self.errors: list[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            mod = alias.name.split(".")[0]
            if mod in FORBIDDEN_MODULES:
                self.errors.append(f"禁止导入模块: {alias.name}")
            elif mod not in ALLOWED_IMPORTS:
                self.errors.append(f"不允许的导入: {alias.name} (仅允许 numpy)")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        mod = node.module or ""
        root = mod.split(".")[0]
        if root in FORBIDDEN_MODULES:
            self.errors.append(f"禁止从 {mod} 导入")
        elif mod not in ALLOWED_FROM_IMPORTS and root not in ALLOWED_IMPORTS:
            self.errors.append(f"不允许的 from 导入: {mod}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_NAMES:
            self.errors.append(f"禁止调用: {node.func.id}()")
        if isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_NAMES:
            self.errors.append(f"禁止调用: .{node.func.attr}()")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if node.id.startswith("__") and node.id.endswith("__") and node.id not in ("__name__",):
            self.errors.append(f"禁止访问 dunder 属性: {node.id}")
        self.generic_visit(node)


def validate_code(code: str, label: str = "strategy") -> None:
    """
    对代码进行 AST 安全检查。
    Raises CodeSafetyError if anything dangerous is found.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise CodeSafetyError(f"{label} 代码语法错误: {e}") from e

    visitor = _SafetyVisitor()
    visitor.visit(tree)
    if visitor.errors:
        raise CodeSafetyError(
            f"{label} 代码安全检查失败:\n" + "\n".join(f"  - {e}" for e in visitor.errors)
        )


def _check_function_exists(code: str, func_name: str) -> bool:
    """检查代码中是否定义了指定函数"""
    tree = ast.parse(code)
    return any(
        isinstance(node, ast.FunctionDef) and node.name == func_name
        for node in ast.walk(tree)
    )


def load_strategy_functions(
    strategy_code: str,
    setup_code: str,
) -> Tuple[Callable, Callable]:
    """
    安全加载 AI 生成的策略代码，返回 (strategy_fn, setup_fn)。
    """
    validate_code(strategy_code, "strategy_fn")
    validate_code(setup_code, "setup_fn")

    if not _check_function_exists(strategy_code, "strategy"):
        raise CodeSafetyError("strategy_fn 代码中必须定义 def strategy(ctx, params=None)")
    if not _check_function_exists(setup_code, "setup"):
        raise CodeSafetyError("setup_fn 代码中必须定义 def setup(ctx)")

    import numpy as np
    from app.services import indicators
    from app.services.strategy_backtest import (
        SMA, EMA, RSI, MACD, BBANDS, ATR,
    )

    safe_globals: Dict[str, Any] = {
        "__builtins__": {
            "range": range,
            "len": len,
            "abs": abs,
            "max": max,
            "min": min,
            "round": round,
            "int": int,
            "float": float,
            "bool": bool,
            "str": str,
            "list": list,
            "dict": dict,
            "tuple": tuple,
            "set": set,
            "enumerate": enumerate,
            "zip": zip,
            "sorted": sorted,
            "reversed": reversed,
            "sum": sum,
            "any": any,
            "all": all,
            "isinstance": isinstance,
            "print": lambda *a, **kw: None,
            "True": True,
            "False": False,
            "None": None,
        },
        "np": np,
        "numpy": np,
        "math": __import__("math"),
        "SMA": SMA, "EMA": EMA, "RSI": RSI, "MACD": MACD,
        "BBANDS": BBANDS, "ATR": ATR,
        "CROSS_ABOVE": indicators.CROSS_ABOVE,
        "CROSS_BELOW": indicators.CROSS_BELOW,
        "HIGHEST": indicators.HIGHEST,
        "LOWEST": indicators.LOWEST,
        "KDJ": indicators.KDJ,
        "OBV": indicators.OBV,
        "STOCH_RSI": indicators.STOCH_RSI,
        "VOLATILITY": indicators.VOLATILITY,
        "VWAP": indicators.VWAP,
        "WMA": indicators.WMA,
        "PERCENT_RANK": indicators.PERCENT_RANK,
    }

    strategy_ns: Dict[str, Any] = dict(safe_globals)
    exec(compile(strategy_code, "<agent-strategy>", "exec"), strategy_ns)
    strategy_fn = strategy_ns["strategy"]

    setup_ns: Dict[str, Any] = dict(safe_globals)
    exec(compile(setup_code, "<agent-setup>", "exec"), setup_ns)
    setup_fn = setup_ns["setup"]

    return strategy_fn, setup_fn
