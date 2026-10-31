"""
回测编排器：把「输入校验 → 数据接入 → 引擎回测 → 指标/守恒/报告」串成一条链路。

入口 run_backtest(request) 返回结构化报告字典；任何输入非法时抛
ValidationError（由 API 层捕获并返回 4xx，绝不带病产出报告）。
"""
import sys
import os
import datetime as dt

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.util.config import get_config
from backend.data import datasource
from backend.engine import validation as V
from backend.engine import backtest as BT
from backend.engine import reconciliation as REC
from backend.engine.exceptions import ValidationError
from backend.strategies import registry
from backend.report import build_report


def _default_symbols(cfg):
    return [dict(s) for s in cfg["universe"]["default_symbols"]]


def _default_benchmark(cfg):
    return dict(cfg["universe"]["benchmark"])


def run_backtest(request: dict) -> dict:
    cfg = get_config()
    strategy_key = request.get("strategy_key")
    params = request.get("params") or {}
    start = request.get("start") or cfg["backtest"]["default_start"]
    end = request.get("end") or cfg["backtest"]["default_end"]
    refresh = bool(request.get("refresh", False))

    # 1) 校验策略参数（先于数据，快速失败）
    if not strategy_key:
        raise ValidationError("未指定策略。", "strategy_key")
    # 先尝试构造策略（会触发策略自身参数校验）
    strategy = registry.build_strategy(strategy_key, params)

    # 2) 解析标的池与基准
    if strategy_key == "sma_dual":
        sym = params.get("symbol")
        at = params.get("asset_type") or _infer_asset_type(sym, cfg)
        symbols = [{"symbol": sym, "asset_type": at}]
    else:
        symbols = request.get("symbols") or _default_symbols(cfg)
    benchmark = request.get("benchmark") or _default_benchmark(cfg)

    # 3) 输入自证（维度 1）
    V.validate_symbols(symbols)
    V.validate_dates(start, end)

    # 4) 接入行情（优先缓存；缺失则联网抓取，限流时快速失败不阻塞）
    bars, meta = datasource.load_market(symbols, start, end, allow_sleep=False, refresh=refresh)
    bench_bars, bench_meta = datasource.load_benchmark(
        benchmark, start, end, allow_sleep=False, refresh=refresh)
    bench_symbol = benchmark["symbol"]

    # 5) 覆盖范围校验（缺失即阻止，绝不静默删除标的）
    V.validate_coverage(symbols, start, end, meta)

    warnings = []
    for s, m in meta.items():
        if m.get("status") != "ok":
            raise ValidationError(f"标的 {s} 数据不可用：{m.get('note')}", "symbols")
        if m.get("review_flag"):
            warnings.append(f"[{s}] {m['review_flag']}")
        if m.get("coverage_warning"):
            warnings.append(f"[{s}] {m['coverage_warning']}")
    if bench_meta.get(bench_symbol, {}).get("status") != "ok":
        warnings.append(f"基准 {bench_symbol} 数据不可用，报告将不含基准对比。")

    # 6) 运行引擎
    engine = BT.BacktestEngine(bars, bench_bars, bench_symbol, cfg, strategy)
    result = engine.run()

    # 7) 守恒校验 + 指纹
    recon = REC.reconcile(result["ledger"], result["daily"], bars, result["universe"],
                          result["initial_capital"])
    fingerprint = BT.build_fingerprint(
        [(s["symbol"], s["asset_type"]) for s in symbols], start, end,
        strategy_key, params, cfg["costs"])

    # 8) 组装报告
    ctx_meta = {
        "strategy_key": strategy_key,
        "strategy_name": getattr(strategy, "name", strategy_key),
        "params": params,
        "symbols": symbols,
        "start": start, "end": end,
        "benchmark": benchmark,
        "initial_capital": result["initial_capital"],
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    data_meta = {"symbols": meta, "benchmark": bench_meta}
    report = build_report(result, cfg, ctx_meta, data_meta, recon, fingerprint)
    report["warnings"] = warnings
    report["source_info"] = datasource.describe_source()
    return report


def _infer_asset_type(code: str, cfg) -> str:
    for s in cfg["universe"]["default_symbols"]:
        if s["symbol"] == code:
            return s["asset_type"]
    if code == cfg["universe"]["benchmark"]["symbol"]:
        return "index"
    if code == cfg["universe"]["etf_example"]["symbol"]:
        return "etf"
    # 兜底：6 开头多为股票，5/1 开头多为 ETF，0/3 开头多为股票
    if code[0] in ("5", "1"):
        return "etf"
    return "stock"
