"""
数据初始化：拉取并缓存默认标的池 / 基准 / ETF 的日线行情到本地（data/cache/*.csv）。

用法：
  python tools/init_data.py            # 常规初始化（限流时快速失败，不阻塞）
  python tools/init_data.py --refresh  # 强制重新联网抓取

说明：Sina 源（个股/指数）稳定；ETF 前复权走东方财富，若被限流会自动回退新浪未复权
并标注「待人工复核」，不会中断。缓存后回测直接读本地，单机可运行、可复现。
"""
import os
import sys
import argparse

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.data import datasource
from backend.util.config import get_config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="强制重新抓取")
    args = ap.parse_args()
    cfg = get_config()
    syms = (cfg["universe"]["default_symbols"]
            + [cfg["universe"]["benchmark"], cfg["universe"]["etf_example"]])
    start, end = cfg["backtest"]["default_start"], cfg["backtest"]["default_end"]
    print(f"初始化数据：{start} ~ {end}，共 {len(syms)} 个标的 ...")
    bars, meta = datasource.load_market(syms, start, end, allow_sleep=False, refresh=args.refresh)
    for s, m in meta.items():
        print(f"  {s}: {m.get('status')} rows={m.get('rows')} adj={m.get('adjust_method')}"
              + (f" ⚠{m.get('review_flag')}" if m.get("review_flag") else ""))
    print("完成。缓存目录：", datasource._cache_dir())


if __name__ == "__main__":
    main()
