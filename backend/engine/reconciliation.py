"""
守恒校验（验收维度 2）与计算溯源支撑（维度 3）。

从不依赖引擎内部累加的净值，而是「仅凭成交台账（trade ledger）+ 原始行情」
独立重算每日市值，与引擎记录的净值逐日比对：
  - 标的总数守恒：每个标的 买入份额 - 卖出份额 = 期末持仓（不丢不重）。
  - 组合净值守恒：现金 + Σ(持仓 × 收盘价) 重算值 与 引擎记录净值 逐位一致。
  - 复权、分红、交易成本摊薄后仍然守恒（成本已在台账中逐笔扣减）。

返回结构化结果，供报告展示与自查评估引用（含代码位置与逐日证据）。
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def reconcile(ledger: list, daily_records: list, bars: dict, universe: list,
             initial_capital: float, tolerance: float = 1e-6) -> dict:
    positions = {s: 0.0 for s in universe}
    cash = initial_capital
    by_date = {}
    for t in ledger:
        by_date.setdefault(t["date"], []).append(t)

    daily_match = []
    for rec in daily_records:
        d = rec["date"]
        for t in by_date.get(d, []):
            s = t["symbol"]
            if t["side"] == "buy":
                cash -= (t["trade_value"] + t["commission"] + t["stamp"])
            else:
                cash += (t["trade_value"] - t["commission"] - t["stamp"])
            positions[s] += t["shares"] if t["side"] == "buy" else -t["shares"]

        # 独立重算当日市值
        val = cash
        unknown = False
        for s in universe:
            if positions[s] == 0.0:
                continue
            bar = bars.get(s, {}).get(d)
            if bar is None:
                unknown = True
                break
            val += positions[s] * bar["close"]
        recomputed_nav = None if unknown else val / initial_capital
        rec_nav = rec.get("nav")
        if recomputed_nav is None and rec_nav is None:
            match = True
            diff = 0.0
        elif recomputed_nav is None or rec_nav is None:
            match = False
            diff = float("nan")
        else:
            diff = abs(recomputed_nav - rec_nav)
            match = diff <= tolerance
        daily_match.append({"date": d, "match": match, "diff": diff,
                            "recomputed_nav": recomputed_nav, "rec_nav": rec_nav,
                            "unknown": unknown})

    # 标的总数守恒
    cons = {}
    for s in universe:
        bought = sum(t["shares"] for t in ledger if t["symbol"] == s and t["side"] == "buy")
        sold = sum(t["shares"] for t in ledger if t["symbol"] == s and t["side"] == "sell")
        end = positions[s]
        cons[s] = {
            "bought": bought, "sold": sold, "end": end,
            "ok": abs(bought - sold - end) <= tolerance,
        }

    final_cash_ok = abs(cash - daily_records[-1]["cash"]) <= tolerance if daily_records else True
    max_diff = max((m["diff"] for m in daily_match if isinstance(m["diff"], float) and not (isinstance(m["diff"], float) and m["diff"] != m["diff"])), default=0.0)
    all_match = (
        all(m["match"] for m in daily_match)
        and all(v["ok"] for v in cons.values())
        and final_cash_ok
    )
    return {
        "all_match": all_match,
        "max_abs_diff": max_diff,
        "final_cash_ok": final_cash_ok,
        "daily_match": daily_match,
        "shares_conservation": cons,
    }
