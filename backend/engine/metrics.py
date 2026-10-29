"""
绩效指标计算与公式定义（验收维度：结果层 + 计算溯源）。

所有指标口径与《365天量化金融》课程定义保持一致，并在本模块显式写出
公式字符串，供报告文档与前端展示引用（不只在代码里，也要写在文档中）。

保守口径（对应约束 2「指标与收益宁可保守，不可虚高」）：
  - 无风险利率取正（默认 2%），拉低夏普，不虚高。
  - 收益与净值已含佣金/印花税/滑点，未做前瞻，天然偏保守。
  - 年化基于 252 交易日。
"""
import math
import sys
import os

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _std(xs):
    return float(np.std(np.array(xs), ddof=0)) if len(xs) > 1 else 0.0


def compute_metrics(daily_records: list, cfg: dict, bench_records=None) -> dict:
    """从日频记录计算核心指标。daily_records 含 nav / unknown_flag 等字段。"""
    known = [r for r in daily_records if not r.get("unknown_flag")]
    n = len(known)
    out = {"n_trading_days": n}
    if n < 2:
        out["error"] = "有效交易日不足，无法计算指标。"
        return out

    navs = [r["nav"] for r in known]
    rets = [navs[i] / navs[i - 1] - 1.0 for i in range(1, n)]
    tdy = cfg["metrics"]["trading_days_per_year"]
    rf = cfg["metrics"]["risk_free_rate"]
    years = n / tdy

    total_ret = navs[-1] / navs[0] - 1.0
    ann_ret = (navs[-1] / navs[0]) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    ann_vol = _std(rets) * math.sqrt(tdy)
    sharpe = (ann_ret - rf) / ann_vol if ann_vol > 1e-12 else None
    # 最大回撤
    peak = navs[0]
    mdd = 0.0
    for v in navs:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > mdd:
            mdd = dd
    calmar = ann_ret / mdd if mdd > 1e-12 else None

    out.update({
        "total_return": total_ret,
        "annualized_return": ann_ret,
        "annualized_volatility": ann_vol,
        "sharpe": sharpe,
        "max_drawdown": mdd,
        "calmar": calmar,
        "final_nav": navs[-1],
        "rf": rf,
        "trading_days_per_year": tdy,
    })

    # 基准对比（若提供）
    if bench_records:
        bknown = [r for r in bench_records if r.get("bench_nav") is not None]
        if len(bknown) >= 2:
            bnavs = [r["bench_nav"] for r in bknown]
            b_ann = (bnavs[-1] / bnavs[0]) ** (1.0 / (len(bknown) / tdy)) - 1.0
            b_rets = [bnavs[i] / bnavs[i - 1] - 1.0 for i in range(1, len(bknown))]
            b_vol = _std(b_rets) * math.sqrt(tdy)
            out["benchmark_annualized_return"] = b_ann
            out["benchmark_annualized_volatility"] = b_vol
            out["benchmark_total_return"] = bnavs[-1] / bnavs[0] - 1.0
            out["excess_annualized_return"] = ann_ret - b_ann

    out["formulas"] = _formula_strings(rf, tdy)
    return out


def _formula_strings(rf, tdy):
    return {
        "净值(NV)": "NV_t = 组合市值_t / 初始资金；初始 NV_0 = 1.0",
        "累计收益率": "累计收益率 = NV_末 / NV_首 - 1",
        "年化收益率": "年化收益率 = (NV_末 / NV_首)^(252 / 交易日数) - 1",
        "日收益率": "r_t = NV_t / NV_{t-1} - 1（仅在相邻两日均可估值时计算，缺失日不跨日计算）",
        "年化波动率": "年化波动率 = std(日收益率) × √252（总体标准差，ddof=0）",
        "夏普比率": f"夏普 = (年化收益率 - 无风险利率) / 年化波动率；无风险利率 rf = {rf}",
        "最大回撤": "最大回撤 = max_t { (历史峰值NV - NV_t) / 历史峰值NV }",
        "卡玛比率": "卡玛 = 年化收益率 / 最大回撤",
        "假设": f"无风险利率={rf}，年交易日={tdy}，成本含佣金/印花税/滑点，无前瞻偏差。",
    }
