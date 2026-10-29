"""
交易成本与市场监管（涨跌停 / 停牌）计算。

设计要点（对应验收约束 2「回测必须诚实」）：
  - 佣金：按成交额计费，单笔不低于最低佣金；买卖双向收取。
  - 印花税：仅卖出方收取（A股规则）。
  - 滑点：双边计入，买卖分别在开盘价基础上加减滑点（保守估计）。
  - 涨跌停：仅在「股票」上施加不可成交约束；涨停不可买、跌停不可卖。
    在「前复权」空间内用涨跌幅比值判断，与未复权比值一致，避免复权误差。
  - 指数/ETF 默认不施加涨跌停约束（已在文档标注为简化项）。
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def compute_trade_cost(side: str, trade_value: float, costs_cfg: dict):
    """返回 (commission, stamp_tax, total_cost)。trade_value 为成交金额。"""
    rate = costs_cfg["commission_rate"]
    min_comm = costs_cfg["min_commission"]
    stamp_rate = costs_cfg["stamp_tax_rate"]
    commission = max(trade_value * rate, min_comm)
    stamp = trade_value * stamp_rate if side == "sell" else 0.0
    return commission, stamp, commission + stamp


def apply_slippage(open_price: float, side: str, slippage_rate: float) -> float:
    """在开盘价基础上施加滑点：买价更高、卖价更低（保守）。"""
    if side == "buy":
        return open_price * (1.0 + slippage_rate)
    return open_price * (1.0 - slippage_rate)


def _limit_category(code: str, limit_rules: dict) -> str:
    """根据代码前缀判定板块（main / star_chinext / st）。"""
    return limit_rules.get(code[:3], limit_rules.get(code[:2], "main"))


def limit_pct_for(code: str, costs_cfg: dict) -> float:
    cat = _limit_category(code, costs_cfg.get("limit_rules", {}))
    return costs_cfg["limit_pct"].get(cat, 0.10)


def detect_limit_status(close: float, prev_close: float, limit_pct: float) -> str:
    """
    返回 'up' / 'down' / 'none'。
    用 (close - prev_close)/prev_close 比值判定（前复权空间内与未复权一致）。
    允许 1e-9 的数值容差。
    """
    if prev_close is None or prev_close <= 0 or close is None:
        return "none"
    ret = (close - prev_close) / prev_close
    if ret >= limit_pct - 1e-9:
        return "up"
    if ret <= -limit_pct + 1e-9:
        return "down"
    return "none"


def is_tradable(side: str, asset_type: str, limit_status: str) -> bool:
    """股票在涨停不可买、跌停不可卖；其余可交易。"""
    if asset_type != "stock":
        return True
    if side == "buy" and limit_status == "up":
        return False
    if side == "sell" and limit_status == "down":
        return False
    return True
