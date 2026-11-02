"""
生成样例回测报告（交付物 ② / ③）。

对同一数据区间（config 默认 2021-01-01 ~ 2023-12-31）跑通三个模板策略，
输出：
  outputs/<key>_report.json      完整回测报告（指标/日频/月度/成交/异常/守恒）
  outputs/<key>_daily_nav.csv    日频净值明细
  outputs/<key>_monthly.csv       月度汇总
  outputs/<key>_nav_curve.svg     净值曲线（策略 vs 基准）
  outputs/sample_backtest_report.md 汇总说明（含指标、假设、公式）

运行：python tools/generate_sample_reports.py
"""
import os
import sys
import json
import csv

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.runner import run_backtest
from backend.util.config import get_config

OUT = os.path.join(_ROOT, "outputs")
os.makedirs(OUT, exist_ok=True)


def write_json(key, report):
    with open(os.path.join(OUT, f"{key}_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)


def write_daily_csv(key, report):
    path = os.path.join(OUT, f"{key}_daily_nav.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "nav", "bench_nav", "daily_return", "cash", "positions_value"])
        for d in report["daily"]:
            w.writerow([d["date"], "" if d["nav"] is None else round(d["nav"], 6),
                        "" if d["bench_nav"] is None else round(d["bench_nav"], 6),
                        "" if d["daily_return"] is None else round(d["daily_return"], 6),
                        round(d["cash"], 2), round(d["positions_value"], 2)])


def write_monthly_csv(key, report):
    path = os.path.join(OUT, f"{key}_monthly.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "month_return", "month_end_nav", "month_max_drawdown", "bench_month_return", "trading_days"])
        for m in report["monthly"]:
            w.writerow([m["month"], m["month_return"], m["month_end_nav"],
                        m["month_max_drawdown"], m["bench_month_return"], m["trading_days"]])


def svg_nav_curve(report, title):
    """用 Python 生成净值曲线 SVG（策略 vs 基准），离线可用。"""
    W, H, padL, padR, padT, padB = 900, 380, 56, 20, 20, 36
    plotW, plotH = W - padL - padR, H - padT - padB
    daily = report["daily"]
    N = len(daily)
    strat = [[i, r["nav"]] for i, r in enumerate(daily) if r["nav"] is not None]
    bench = [[i, r["bench_nav"]] for i, r in enumerate(daily) if r["bench_nav"] is not None]
    vals = [p[1] for p in strat] + [p[1] for p in bench] + [1.0]
    minV, maxV = min(vals), max(vals)
    if minV == maxV:
        minV -= 0.05; maxV += 0.05
    xAt = lambda i: padL + (i / (N - 1)) * plotW
    yAt = lambda v: padT + (maxV - v) / (maxV - minV) * plotH

    def path(arr, color):
        if not arr:
            return ""
        d = "M" + " L".join(f"{xAt(p[0]):.1f} {yAt(p[1]):.1f}" for p in arr)
        return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.8"/>'

    g = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif">']
    for t in range(5):
        v = minV + (maxV - minV) * t / 4
        y = yAt(v)
        g.append(f'<line x1="{padL}" y1="{y:.1f}" x2="{W-padR}" y2="{y:.1f}" stroke="#eceff3"/>')
        g.append(f'<text x="{padL-6}" y="{y+4:.1f}" text-anchor="end" font-size="11" fill="#6b7280">{v:.2f}</text>')
    y1 = yAt(1.0)
    g.append(f'<line x1="{padL}" y1="{y1:.1f}" x2="{W-padR}" y2="{y1:.1f}" stroke="#9ca3af" stroke-dasharray="4 4"/>')
    g.append(path(bench, "#ea580c"))
    g.append(path(strat, "#2563eb"))
    g.append(f'<rect x="{W-240}" y="{padT}" width="12" height="12" fill="#2563eb"/><text x="{W-224}" y="{padT+10}" font-size="12">策略净值</text>')
    g.append(f'<rect x="{W-130}" y="{padT}" width="12" height="12" fill="#ea580c"/><text x="{W-114}" y="{padT+10}" font-size="12">基准(沪深300)</text>')
    g.append(f'<text x="{padL}" y="{H-12}" font-size="12" fill="#374151">{title}</text>')
    g.append('</svg>')
    return "\n".join(g)


def write_svg(key, report, title):
    with open(os.path.join(OUT, f"{key}_nav_curve.svg"), "w", encoding="utf-8") as f:
        f.write(svg_nav_curve(report, title))


def main():
    cfg = get_config()
    start, end = cfg["backtest"]["default_start"], cfg["backtest"]["default_end"]
    bench = cfg["universe"]["benchmark"]
    plans = [
        ("buy_hold", "买入持有（默认池：茅台/平安/招行）", {"strategy_key": "buy_hold", "params": {}}),
        ("sma_dual", "SMA双均线（沪深300, 快5/慢20）", {"strategy_key": "sma_dual",
            "params": {"symbol": bench["symbol"], "asset_type": bench["asset_type"], "fast": 5, "slow": 20}}),
        ("monthly_rebalance", "月度再平衡（默认池）", {"strategy_key": "monthly_rebalance", "params": {}}),
    ]
    summary = []
    for key, title, req in plans:
        req = dict(req); req["start"] = start; req["end"] = end
        print(f"运行 {key} ...")
        rep = run_backtest(req)
        write_json(key, rep)
        write_daily_csv(key, rep)
        write_monthly_csv(key, rep)
        write_svg(key, rep, title)
        m = rep["metrics"]
        summary.append((key, title, rep, m))

    # 汇总 Markdown
    md = ["# 样例回测报告（三模板策略同区间对比）", "",
          f"> 数据区间：**{start} ~ {end}** ｜ 初始资金：{cfg['backtest']['initial_capital']:,.0f} 元 ｜ 复权：{cfg['data']['adjust']} ｜ 基准：沪深300",
          "> 说明：以下为真实历史数据回测结果（A股 2021–2023 熊市区间），所有收益已含佣金/印花税/滑点，无前瞻偏差，口径保守。", "",
          "## 一、核心指标对比", "",
          "| 策略 | 累计收益 | 年化收益 | 年化波动 | 夏普 | 最大回撤 | 卡玛 | 成交笔数 |",
          "|---|---|---|---|---|---|---|---|"]
    for key, title, rep, m in summary:
        md.append(f"| {title} | {m['total_return']*100:.2f}% | {m['annualized_return']*100:.2f}% | "
                  f"{m['annualized_volatility']*100:.2f}% | {m['sharpe']:.3f} | {m['max_drawdown']*100:.2f}% | "
                  f"{m['calmar']:.3f} | {rep['trade_stats']['num_trades']} |")
    md += ["", "## 二、净值曲线（策略 vs 基准）", ""]
    for key, title, rep, m in summary:
        md.append(f"### {title}")
        md.append(f"![{title}]({key}_nav_curve.svg)")
        md.append("")
    md += ["## 三、回测假设（指标口径，详见 docs/metric_formulas.md）", ""]
    md.append(f"- 无风险利率 rf = {cfg['metrics']['risk_free_rate']*100:.1f}%（取正，拉低夏普，保守）")
    md.append(f"- 年交易日 = {cfg['metrics']['trading_days_per_year']}；年化 = (末/首)^(252/天数) − 1")
    md.append(f"- 佣金 {cfg['costs']['commission_rate']*100:.2f}%（单笔最低 {cfg['costs']['min_commission']} 元）、印花税（仅卖出）{cfg['costs']['stamp_tax_rate']*100:.2f}%、滑点 {cfg['costs']['slippage_rate']*100:.1f}%（双边）")
    md.append("- 成交规则：**信号于第 t 日收盘生成，成交于第 t+1 日开盘执行**（无前瞻偏差）；前复权价；涨停不可买、跌停不可卖。")
    md.append("")
    md.append("## 四、守恒校验与异常（维度2/5/6）")
    for key, title, rep, m in summary:
        rec = rep["reconciliation"]
        anom = sum(a["count"] for a in rep["anomalies"].values())
        md.append(f"- **{title}**：逐日净值对账 {('✅一致' if rec['all_match'] else '❌不一致')}（最大偏差 {rec['max_abs_diff']:.2e}），"
                  f"期末现金对账 {'✅' if rec['final_cash_ok'] else '❌'}，异常 {anom} 条（见各报告 JSON）。")
    md.append("")
    md.append("## 五、交付文件")
    md.append("- `outputs/<key>_report.json`：完整报告（指标/日频/月度/成交/异常/守恒）")
    md.append("- `outputs/<key>_daily_nav.csv`：日频净值明细")
    md.append("- `outputs/<key>_monthly.csv`：月度汇总")
    md.append("- `outputs/<key>_nav_curve.svg`：净值曲线")
    md.append("")
    md.append("> 复现命令：`python tools/generate_sample_reports.py`（需先 `python tools/init_data.py` 初始化数据）。")
    with open(os.path.join(OUT, "sample_backtest_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print("样例报告已生成至 outputs/")


if __name__ == "__main__":
    main()
