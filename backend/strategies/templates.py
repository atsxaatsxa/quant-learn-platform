"""
三个内置模板策略（参数化，新手无需写代码）。

对应《365天量化金融》三大基础策略范式：买入持有 / SMA 双均线 / 月度再平衡。
每个策略的讲解文案放在 course_ref，由教学层按步骤展示给新手。
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.strategies.base import BaseStrategy
from backend.engine.exceptions import ValidationError


class BuyHoldStrategy(BaseStrategy):
    key = "buy_hold"
    name = "买入持有（Buy & Hold）"
    description = "回测期初等权重买入一篮子标的并持有到期，不做任何调仓。"
    course_ref = (
        "课程第29讲·三大基础策略范式之一：买入持有。\n"
        "白话：像定投一支基金那样，期初一次性买好、然后一直拿着，不折腾。\n"
        "它用来建立「基准认知」——连调仓都不做能赚多少，方便和后面会动的手艺对比。"
    )

    def initialize(self, ctx):
        n = len(ctx.universe)
        if n == 0:
            return None
        w = 1.0 / n
        return {s: w for s in ctx.universe}

    def decide(self, date, ctx):
        return None  # 持有到底，不再调仓

    def param_schema(self):
        return [
            {"key": "weight_mode", "label": "仓位方式", "type": "choice",
             "options": [{"value": "equal", "label": "等权重（默认）"}],
             "default": "equal", "help": "期初将所有资金均分买入全部标的。"},
        ]

    def validate_params(self, params):
        if params.get("weight_mode", "equal") != "equal":
            raise ValidationError("买入持有仅支持等权重。", "weight_mode")


class SMADualStrategy(BaseStrategy):
    key = "sma_dual"
    name = "SMA 双均线（快慢均线交叉）"
    description = "对单一标的，当短期均线高于长期均线时满仓，否则空仓；金叉买入、死叉卖出。"
    course_ref = (
        "课程第29讲·三大基础策略范式之二：SMA 双均线（移动平均线交叉）。\n"
        "白话：均线就是把过去 N 天收盘价取平均画成一条线。短期线（快）上穿长期线（慢）=「金叉」，"
        "说明涨势强，买入；反过来「死叉」卖出。它是最经典的「趋势跟随」入门策略。"
    )

    def __init__(self):
        self._symbol = None

    def initialize(self, ctx):
        return None  # 等首个信号出现再进场

    def decide(self, date, ctx):
        sym = self._symbol
        if sym is None:
            return None
        closes = ctx.closes(sym, date)
        if len(closes) < self._slow:
            return None
        fast_ma = sum(closes[-self._fast:]) / self._fast
        slow_ma = sum(closes[-self._slow:]) / self._slow
        return {sym: 1.0} if fast_ma > slow_ma else {sym: 0.0}

    def param_schema(self):
        from backend.util.config import get_config
        cfg = get_config()
        # 可选标的：默认池 + 基准 + ETF
        opts = [{"value": s["symbol"], "label": f'{s["name"]}({s["symbol"]})'}
                for s in cfg["universe"]["default_symbols"]]
        opts.append({"value": cfg["universe"]["benchmark"]["symbol"],
                     "label": f'{cfg["universe"]["benchmark"]["name"]}({cfg["universe"]["benchmark"]["symbol"]})'})
        opts.append({"value": cfg["universe"]["etf_example"]["symbol"],
                     "label": f'{cfg["universe"]["etf_example"]["name"]}({cfg["universe"]["etf_example"]["symbol"]})'})
        return [
            {"key": "symbol", "label": "交易标的", "type": "choice", "options": opts,
             "default": cfg["universe"]["benchmark"]["symbol"],
             "help": "双均线策略在单一标的上运行（默认沪深300指数）。"},
            {"key": "fast", "label": "短期均线周期(天)", "type": "int", "default": 5,
             "min": 1, "max": 250, "step": 1,
             "help": "短期均线窗口，如 5 表示最近 5 个交易日平均价。"},
            {"key": "slow", "label": "长期均线周期(天)", "type": "int", "default": 20,
             "min": 2, "max": 500, "step": 1,
             "help": "长期均线窗口，须大于短期周期。"},
        ]

    def validate_params(self, params):
        sym = params.get("symbol")
        if not isinstance(sym, str) or not sym.isdigit() or len(sym) != 6:
            raise ValidationError("交易标的应为 6 位数字代码。", "symbol")
        fast = params.get("fast")
        slow = params.get("slow")
        if not isinstance(fast, int) or fast < 1:
            raise ValidationError("短期均线周期必须为 >=1 的整数。", "fast")
        if not isinstance(slow, int) or slow <= fast:
            raise ValidationError("长期均线周期必须为整数且大于短期周期。", "slow")

    def bind(self, params):
        self._symbol = params.get("symbol")
        self._fast = int(params.get("fast", 5))
        self._slow = int(params.get("slow", 20))


class MonthlyRebalanceStrategy(BaseStrategy):
    key = "monthly_rebalance"
    name = "月度再平衡（Monthly Rebalance）"
    description = "期初等权重建仓，之后每个月的第一个交易日重新调回等权重。"
    course_ref = (
        "课程第29讲·三大基础策略范式之三：月度再平衡。\n"
        "白话：月初把篮子里的各项重新调回一样的比例。比如茅台涨多了、平安跌多了，"
        "比例就歪了，再平衡就是把它们「掰回」初始比例——相当于自动「高抛低吸」一点。\n"
        "它教的是「纪律性调仓」，也是很多资产配置策略的骨架。"
    )

    def __init__(self):
        self._last_month = None
        self._weights = None

    def initialize(self, ctx):
        n = len(ctx.universe)
        if n == 0:
            return None
        w = 1.0 / n
        self._weights = {s: w for s in ctx.universe}
        return dict(self._weights)

    def decide(self, date, ctx):
        m = date[:7]  # YYYY-MM
        if m != self._last_month:
            self._last_month = m
            return dict(self._weights)  # 每月首个交易日再平衡
        return None

    def param_schema(self):
        return [
            {"key": "rebalance", "label": "再平衡频率", "type": "choice",
             "options": [{"value": "monthly", "label": "每月首个交易日（默认）"}],
             "default": "monthly", "help": "在每月第一个交易日把组合调回等权重。"},
        ]

    def validate_params(self, params):
        if params.get("rebalance", "monthly") != "monthly":
            raise ValidationError("月度再平衡仅支持每月再平衡。", "rebalance")
