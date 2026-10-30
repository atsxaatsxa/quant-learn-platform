"""
策略注册表：模板策略 + 进阶「代码编辑入口」。

- 模板策略：买入持有 / SMA 双均线 / 月度再平衡（参数化，无需写代码）。
- 代码模式：进阶用户提交一段 Python（定义 initialize/decide），在受限命名空间执行。
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.strategies.base import BaseStrategy
from backend.strategies.templates import (
    BuyHoldStrategy, SMADualStrategy, MonthlyRebalanceStrategy,
)
from backend.engine.exceptions import ValidationError

STRATEGIES = {
    "buy_hold": BuyHoldStrategy,
    "sma_dual": SMADualStrategy,
    "monthly_rebalance": MonthlyRebalanceStrategy,
}

# 代码模式默认示例代码（进阶入口展示用）
SAMPLE_CODE = '''# 进阶：自定义策略（代码编辑入口）
# 可用：ctx.universe (标的列表), ctx.closes(symbol, date) -> 截至date的收盘价列表,
#       ctx.bar(symbol, date) -> 当日行情。返回 {标的: 权重} 或 None(不调仓)。

def initialize(ctx):
    # 期初等权买入全部标的
    n = len(ctx.universe)
    return {s: 1.0 / n for s in ctx.universe} if n else None

def decide(date, ctx):
    # 示例：任意标的 20 日均线向上则保持，否则清仓（仅为演示代码结构）
    sym = ctx.universe[0]
    closes = ctx.closes(sym, date)
    if len(closes) < 20:
        return None
    ma20 = sum(closes[-20:]) / 20
    return {sym: 1.0} if closes[-1] > ma20 else {sym: 0.0}
'''


class CodeModeStrategy(BaseStrategy):
    key = "code"
    name = "自定义代码策略（进阶）"

    def __init__(self, code: str, params: dict = None):
        safe_builtins = {
            "sum": sum, "len": len, "range": range, "abs": abs,
            "min": min, "max": max, "float": float, "int": int,
            "round": round, "list": list, "dict": dict, "tuple": tuple,
            "True": True, "False": False, "None": None,
        }
        ns = {}
        try:
            exec(code, {"__builtins__": safe_builtins}, ns)
        except Exception as e:  # noqa
            raise ValidationError(f"代码执行出错：{e}", "code")
        self._init = ns.get("initialize")
        self._decide = ns.get("decide")
        self._validate = ns.get("validate_params")
        if not callable(self._decide):
            raise ValidationError("代码必须定义可调用函数 decide(date, ctx)。", "code")

    def initialize(self, ctx):
        return self._init(ctx) if callable(self._init) else None

    def decide(self, date, ctx):
        return self._decide(date, ctx)

    def validate_params(self, params):
        if callable(self._validate):
            self._validate(params)


def get_template_meta() -> list:
    """供前端渲染模板列表与参数表单。"""
    meta = []
    for key, cls in STRATEGIES.items():
        inst = cls()
        meta.append({
            "key": key, "name": inst.name, "description": inst.description,
            "course_ref": inst.course_ref, "param_schema": inst.param_schema(),
        })
    return meta


def build_strategy(strategy_key: str, params: dict) -> BaseStrategy:
    """按 key + 参数构造策略实例（含参数校验，失败抛 ValidationError）。"""
    if strategy_key == "code":
        code = params.get("code", "")
        if not code.strip():
            raise ValidationError("代码模式需要提交策略代码。", "code")
        return CodeModeStrategy(code, params)
    cls = STRATEGIES.get(strategy_key)
    if cls is None:
        raise ValidationError(f"未知策略：{strategy_key}", "strategy")
    inst = cls()
    inst.validate_params(params or {})
    if hasattr(inst, "bind"):
        inst.bind(params or {})
    return inst
