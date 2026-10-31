"""
回测报告组装（结果层）。

产出结构化报告字典，供 API / 前端 / 文档复用：
  - meta：本次运行的关键假设与参数（可复现）
  - daily：日频净值明细（含基准净值）
  - monthly：月度汇总（月收益、月末净值、月内最大回撤）
  - trades：成交明细台账（每笔可追溯）
  - metrics：核心指标 + 公式
  - anomalies：异常单独分组展示（维度 5/6）
  - reconciliation：守恒校验结果（维度 2）
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.engine import metrics as M
from backend.engine import reconciliation as R


def _monthly_summary(daily: list) -> list:
    months = {}
    for r in daily:
        if r.get("nav") is None:
            continue
        ym = r["date"][:7]
        months.setdefault(ym, []).append(r)
    out = []
    for ym in sorted(months.keys()):
        recs = months[ym]
        first = recs[0]["nav"]
        last = recs[-1]["nav"]
        month_ret = last / first - 1.0 if first else None
        # 月内最大回撤
        peak = recs[0]["nav"]
        mdd = 0.0
        for x in recs:
            if x["nav"] > peak:
                peak = x["nav"]
            dd = (peak - x["nav"]) / peak
            if dd > mdd:
                mdd = dd
        # 基准月收益
        bfirst = next((x["bench_nav"] for x in recs if x.get("bench_nav") is not None), None)
        blast = next((x["bench_nav"] for x in reversed(recs) if x.get("bench_nav") is not None), None)
        bench_ret = (blast / bfirst - 1.0) if (bfirst and blast) else None
        out.append({
            "month": ym,
            "month_return": round(month_ret, 6) if month_ret is not None else None,
            "month_end_nav": round(last, 6),
            "month_max_drawdown": round(mdd, 6),
            "bench_month_return": round(bench_ret, 6) if bench_ret is not None else None,
            "trading_days": len(recs),
        })
    return out


def _trade_stats(ledger: list) -> dict:
    n = len(ledger)
    buys = [t for t in ledger if t["side"] == "buy"]
    sells = [t for t in ledger if t["side"] == "sell"]
    total_cost = sum(t["commission"] + t["stamp"] for t in ledger)
    win = [t for t in sells if t.get("realized_pnl") is not None and t["realized_pnl"] > 0]
    win_rate = (len(win) / len(sells)) if sells else None
    return {
        "num_trades": n,
        "num_buys": len(buys),
        "num_sells": len(sells),
        "total_cost": round(total_cost, 2),
        "win_rate": round(win_rate, 4) if win_rate is not None else None,
    }


def _group_anomalies(anomalies: list) -> dict:
    cats = {
        "data_issue": ("数据/估值异常（待人工复核）", []),
        "market_constraint": ("市场监管约束（涨跌停/停牌导致未成交）", []),
        "abnormal_return": ("异常收益（疑似复权/对齐错误）", []),
    }
    for a in anomalies:
        t = a.get("type")
        if t in ("no_price", "valuation_estimate", "valuation_unknown", "skip_trade"):
            cats["data_issue"][1].append(a)
        elif t == "limit":
            cats["market_constraint"][1].append(a)
        elif t == "abnormal_return":
            cats["abnormal_return"][1].append(a)
        else:
            cats["data_issue"][1].append(a)
    return {k: {"label": v[0], "items": v[1], "count": len(v[1])} for k, v in cats.items()}


def build_report(engine_result: dict, cfg: dict, ctx_meta: dict,
                data_meta: dict, recon: dict, fingerprint: str) -> dict:
    daily = engine_result["daily"]
    ledger = engine_result["ledger"]
    anomalies = engine_result["anomalies"]

    metrics = M.compute_metrics(daily, cfg, bench_records=daily)
    monthly = _monthly_summary(daily)
    trade_stats = _trade_stats(ledger)
    grouped = _group_anomalies(anomalies)

    assumptions = {
        "risk_free_rate": cfg["metrics"]["risk_free_rate"],
        "trading_days_per_year": cfg["metrics"]["trading_days_per_year"],
        "commission_rate": cfg["costs"]["commission_rate"],
        "min_commission": cfg["costs"]["min_commission"],
        "stamp_tax_rate": cfg["costs"]["stamp_tax_rate"],
        "slippage_rate": cfg["costs"]["slippage_rate"],
        "adjust": cfg["data"]["adjust"],
        "execution_rule": "信号于第 t 日收盘生成，成交于第 t+1 日开盘执行（无前瞻）；价格用前复权。",
        "limit_rules": cfg["costs"]["limit_rules"],
        "limit_pct": cfg["costs"]["limit_pct"],
        "initial_capital": engine_result["initial_capital"],
    }

    return {
        "meta": ctx_meta,
        "assumptions": assumptions,
        "data_meta": data_meta,
        "metrics": metrics,
        "monthly": monthly,
        "daily": daily,
        "trades": ledger,
        "trade_stats": trade_stats,
        "anomalies": grouped,
        "reconciliation": recon,
        "fingerprint": fingerprint,
    }
