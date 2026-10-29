"""
输入自证（验收维度 1）。

在回测执行前，对以下三类输入做前置校验；任何异常必须明确报警并
阻止运行，绝不带病输出报告（一票否决项）：
  - 标的池：代码合法性（6 位数字 + 已知资产类型）、是否存在（数据可用）。
  - 回测日期：格式 YYYY-MM-DD、先后顺序、是否超出数据覆盖范围。
  - 策略参数：周期、仓位、频率等，按策略各自规则校验。
"""
import re
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.engine.exceptions import ValidationError

_SYMBOL_RE = re.compile(r"^\d{6}$")
_KNOWN_ASSET_TYPES = {"stock", "index", "etf"}


def validate_symbols(symbol_specs: list) -> None:
    if not symbol_specs:
        raise ValidationError("标的池为空，请至少选择一个标的。", "symbols")
    for spec in symbol_specs:
        sym = spec.get("symbol")
        at = spec.get("asset_type")
        if not isinstance(sym, str) or not _SYMBOL_RE.match(sym):
            raise ValidationError(f"标的代码非法：{sym}（应为 6 位数字）", "symbols")
        if at not in _KNOWN_ASSET_TYPES:
            raise ValidationError(f"未知资产类型：{at}（应为 stock/index/etf）", "symbols")


def validate_dates(start: str, end: str) -> None:
    import datetime as dt
    for name, v in (("start", start), ("end", end)):
        try:
            dt.datetime.strptime(v, "%Y-%m-%d")
        except Exception:
            raise ValidationError(f"日期格式非法：{v}（应为 YYYY-MM-DD）", name)
    if start > end:
        raise ValidationError(f"回测起点 {start} 晚于终点 {end}，顺序错误。", "start")


def validate_coverage(symbol_specs: list, start: str, end: str, meta: dict) -> None:
    """
    校验每个标的的数据可用性。规则：
      - status 必须为 'ok'，否则（error/empty）直接报错阻止。
      - 标的在 [start, end] 区间内必须有数据；若首个数据日 > start，给出提示
        （引擎将从首个可用日起算，不静默删除标的）；若末数据日 < end，区间被截断并提示。
    注意：内部交易日缺失（停牌）由引擎按「无行情/停牌」逐日标注，不在此阻断。
    """
    for spec in symbol_specs:
        sym = spec["symbol"]
        m = meta.get(sym)
        if m is None or m.get("status") != "ok":
            note = m.get("note") if m else "元数据缺失"
            raise ValidationError(
                f"标的 {sym} 数据不可用（{note}），无法回测。请检查代码或重新初始化数据。",
                "symbols",
            )
        fd, ld = m.get("first_date"), m.get("last_date")
        if fd is None or ld is None:
            raise ValidationError(f"标的 {sym} 无有效行情区间。", "symbols")
        if fd > end:
            raise ValidationError(
                f"标的 {sym} 最早数据 {fd} 晚于回测终点 {end}，区间内无数据。", "end")
        if ld < start:
            raise ValidationError(
                f"标的 {sym} 最晚数据 {ld} 早于回测起点 {start}，区间内无数据。", "start")
        # 区间截断提示（非阻断）：若数据覆盖小于请求区间
        if fd > start:
            # 仅记录提示，由调用方收集为 warning（不阻断）
            m["coverage_warning"] = f"数据自 {fd} 起，早于起点的 {start} 部分缺失（将从 {fd} 起算）。"
        if ld < end:
            m.setdefault("coverage_warning", "")
            m["coverage_warning"] = (m.get("coverage_warning", "") +
                                     f" 数据至 {ld} 止，晚于终点的部分缺失（区间截断至 {ld}）。").strip()


def validate_strategy_params(strategy_key: str, params: dict, strategy_validator) -> None:
    """调用具体策略的参数校验器。"""
    if strategy_validator is not None:
        strategy_validator(params)
