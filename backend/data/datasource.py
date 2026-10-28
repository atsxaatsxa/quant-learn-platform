"""
数据层：免费公开行情接入 + 本地缓存 + 复权说明。

数据源选择（含取舍理由，详见 docs/operation_guide.md）：
  - A股个股：akshare.stock_zh_a_daily（新浪源，支持前复权 qfq）。
      取舍：新浪源稳定、不易触发东方财富限流；前复权价便于直接做收益与
      净值计算，避免「用不复权价直接算历史收益」的常见错误。
  - 指数（如沪深300）：akshare.stock_zh_a_daily（新浪源，不调整）。
      取舍：价格指数本身不含拆送股调整；本平台基准使用价格指数买卖持有，
      不计入分红再投资（保守口径，已在文档标注）。
  - ETF：主用 akshare.fund_etf_hist_em（东方财富，支持前复权 qfq）；
      若东方财富限流/失败，回退 akshare.fund_etf_hist_sina（未复权），
      并显式打标「待人工复核：ETF 前复权获取失败，使用新浪未复权数据」——
      绝不静默伪装成前复权（对应验收维度 3/6）。

关键约束（对应验收维度 4「匹配鲁棒」）：
  - 行情以「标的代码 + 日期」为键存取，绝不用行位置/下标对齐。
  - 缺失数据显式标注为「无行情」或「待人工复核」，绝不用前值/0/插值填充。

更新机制：首次运行从网络拉取并缓存到 data/cache/*.csv；再次运行直接读缓存。
需更新数据时重新执行数据初始化（refresh=True）即可。
"""
import os
import sys
import time

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import akshare as ak
from backend.util.config import get_config

# 标准化列
_BAR_COLS = ["date", "open", "high", "low", "close", "volume", "amount"]


def _cache_dir() -> str:
    cfg = get_config()
    d = cfg["data"]["cache_dir"]
    path = d if os.path.isabs(d) else os.path.join(_ROOT, d)
    os.makedirs(path, exist_ok=True)
    return path


def _cache_path(asset_type: str, symbol: str, adjust: str) -> str:
    return os.path.join(_cache_dir(), f"{asset_type}_{symbol}_{adjust}.csv")


def _sina_exchange(code: str, asset_type: str = "stock") -> str:
    """新浪代码前缀（按资产类型区分，因 000xxx 个股在深市、000xxx 指数在上交所）：

      - stock：6/9 开头 -> sh；其余(0/3/2...) -> sz
      - index：0/6 开头 -> sh；3 开头 -> sz
      - etf  ：5/6 开头 -> sh；1 开头 -> sz
    """
    if asset_type == "index":
        return "sh" if code[0] in ("0", "6") else "sz"
    if asset_type == "etf":
        return "sh" if code[0] in ("5", "6") else "sz"
    # stock
    return "sh" if code[0] in ("6", "9") else "sz"


def _norm_dates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df


def _save_cache(path: str, df: pd.DataFrame):
    df = df[_BAR_COLS].copy()
    df.to_csv(path, index=False, encoding="utf-8")


def _load_cache(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"date": str})
    # 确保数值列为 float
    for c in ["open", "high", "low", "close", "volume", "amount"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _is_rate_limit(err) -> bool:
    s = str(err)
    return ("RateLimit" in type(err).__name__) or ("限流" in s) or ("Push2" in s)


def _call_with_retry(fn, retries: int, cooldown_sec: int, allow_sleep: bool):
    """带退避的调用；仅在 allow_sleep=True 时真正睡眠等待（用于离线初始化）。"""
    last = None
    for attempt in range(max(1, retries)):
        try:
            return fn()
        except Exception as e:  # noqa
            last = e
            if _is_rate_limit(e) and allow_sleep and attempt < retries - 1:
                time.sleep(cooldown_sec)
                continue
            raise
    raise last


# ------------------------- 各资产类型抓取 -------------------------
def _fetch_stock(symbol: str, start: str, end: str, adjust: str, allow_sleep: bool):
    s = _sina_exchange(symbol, "stock")

    def _call():
        return ak.stock_zh_a_daily(
            symbol=f"{s}{symbol}", start_date=start.replace("-", ""),
            end_date=end.replace("-", ""), adjust=adjust,
        )

    df = _call_with_retry(_call, 1, 0, allow_sleep)  # 新浪源基本不限流
    return df, {"source": "sina:stock_zh_a_daily", "adjust_method": adjust}


def _fetch_index(symbol: str, start: str, end: str, allow_sleep: bool):
    s = _sina_exchange(symbol, "index")

    def _call():
        return ak.stock_zh_a_daily(
            symbol=f"{s}{symbol}", start_date=start.replace("-", ""),
            end_date=end.replace("-", ""), adjust="",
        )

    df = _call_with_retry(_call, 1, 0, allow_sleep)
    return df, {"source": "sina:stock_zh_a_daily(index)", "adjust_method": "none(price index)"}


def _fetch_etf(symbol: str, start: str, end: str, adjust: str, allow_sleep: bool, retries: int, cooldown: int):
    s = _sina_exchange(symbol, "etf")
    # 主用：东方财富前复权
    try:
        def _em():
            return ak.fund_etf_hist_em(
                symbol=symbol, period="daily",
                start_date=start.replace("-", ""), end_date=end.replace("-", ""),
                adjust=adjust,
            )

        df = _call_with_retry(_em, retries, cooldown, allow_sleep)
        return df, {"source": "em:fund_etf_hist_em", "adjust_method": adjust, "review_flag": None}
    except Exception as e:  # noqa
        if not _is_rate_limit(e):
            raise
        # 限流/失败 -> 回退新浪（未复权），显式标注待复核
        df = ak.fund_etf_hist_sina(symbol=f"{s}{symbol}")
        return df, {
            "source": "sina:fund_etf_hist_sina(fallback)",
            "adjust_method": "unadjusted(backup)",
            "review_flag": "待人工复核：东方财富ETF前复权获取失败(限流)，已回退新浪未复权数据，复权口径不一致，请勿直接用于收益结论。",
        }


# ------------------------- 对外接口 -------------------------
def _dispatch_fetch(spec: dict, start: str, end: str, adjust: str, allow_sleep: bool, retries: int, cooldown: int):
    at = spec["asset_type"]
    sym = spec["symbol"]
    if at == "stock":
        return _fetch_stock(sym, start, end, adjust, allow_sleep)
    if at == "index":
        return _fetch_index(sym, start, end, allow_sleep)
    if at == "etf":
        return _fetch_etf(sym, start, end, adjust, allow_sleep, retries, cooldown)
    raise ValueError(f"未知 asset_type: {at}")


def load_market(symbols: list, start: str, end: str, adjust: str = None,
                allow_sleep: bool = False, refresh: bool = False) -> tuple:
    """
    加载一组标的的日线行情。

    参数：
      symbols: list of {symbol, asset_type, name?}
      start/end: 'YYYY-MM-DD'
      adjust: 复权方式（默认读 config）
      allow_sleep: 是否允许在限流时睡眠等待（离线初始化用）
      refresh: True 时强制重新联网抓取，忽略缓存

    返回：
      bars:  {symbol: {date_str: {open,high,low,close,volume,amount, asset_type}}}
      meta:  {symbol: {asset_type, source, adjust_method, status, note, review_flag}}
    """
    cfg = get_config()
    if adjust is None:
        adjust = cfg["data"]["adjust"]
    retries = cfg["data"].get("em_max_retries", 3)
    cooldown = cfg["data"].get("em_rate_limit_cooldown_sec", 60)

    bars, meta = {}, {}
    for spec in symbols:
        sym = spec["symbol"]
        at = spec["asset_type"]
        cache = _cache_path(at, sym, adjust if at != "index" else "none")
        df, info = None, {}
        # 1) 读缓存
        if (not refresh) and os.path.exists(cache):
            try:
                df = _load_cache(cache)
            except Exception:  # noqa
                df = None
        # 2) 联网抓取
        if df is None or len(df) == 0:
            try:
                raw, info = _dispatch_fetch(spec, start, end, adjust, allow_sleep, retries, cooldown)
                if raw is not None and len(raw) > 0:
                    df = _norm_dates(raw)
                    df = df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)
                    _save_cache(cache, df)
            except Exception as e:  # noqa
                meta[sym] = {"asset_type": at, "status": "error",
                             "note": f"数据获取失败：{str(e)[:200]}"}
                continue
        if df is None or len(df) == 0:
            meta[sym] = {"asset_type": at, "status": "empty",
                         "note": "无行情数据（接口返回为空）"}
            continue
        # 3) 转成 (symbol,date) 键字典
        b = {}
        for _, row in df.iterrows():
            b[row["date"]] = {
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
                "volume": float(row["volume"]) if pd.notna(row["volume"]) else 0.0,
                "amount": float(row["amount"]) if pd.notna(row["amount"]) else 0.0,
                "asset_type": at,
            }
        bars[sym] = b
        meta[sym] = {
            "asset_type": at, "status": "ok",
            "source": info.get("source"), "adjust_method": info.get("adjust_method"),
            "review_flag": info.get("review_flag"),
            "rows": len(b),
            "first_date": min(b.keys()), "last_date": max(b.keys()),
        }
    return bars, meta


def load_benchmark(spec: dict, start: str, end: str, allow_sleep: bool = False,
                   refresh: bool = False) -> tuple:
    """加载基准行情（与 load_market 同接口，便于统一处理）。"""
    return load_market([spec], start, end, adjust=None, allow_sleep=allow_sleep, refresh=refresh)


def describe_source() -> dict:
    """返回数据源说明（供前端/文档展示）。"""
    return {
        "stock": "akshare.stock_zh_a_daily（新浪源，前复权 qfq）",
        "index": "akshare.stock_zh_a_daily（新浪源，价格指数不调整）",
        "etf": "主用 akshare.fund_etf_hist_em（东方财富，前复权）；限流时回退新浪未复权并标注",
        "adjust": "qfq（前复权）",
        "cache": _cache_dir(),
        "fields": _BAR_COLS,
        "update_mechanism": "首次联网抓取并缓存至 data/cache/*.csv；refresh=True 重新拉取。",
        "known_limits": [
            "新浪源对部分退市/极少交易标的历史可能不全；",
            "指数使用价格指数，未含分红再投资（保守口径）；",
            "ETF 前复权依赖东方财富，限流时会回退未复权并标注待复核；",
            "默认交易池为示意性选取，非无幸存者偏差的历史全集（详见 docs）。",
        ],
    }
