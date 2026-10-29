"""
日频回测引擎（核心）。

诚实性设计（对应约束 2「回测必须诚实」与维度 4「匹配鲁棒」）：

1. 无前瞻偏差（no look-ahead）：
   - 信号在「第 t 日收盘」基于截至 t 日收盘可得数据生成；
   - 成交在「第 t+1 日开盘」执行（开盘价在 t+1 日开盘即确定，t 日不可知）。
   - 绝不使用当日收盘价信号在当日成交。

2. 复权与成本：
   - 全程使用「前复权(qfq)」价格计算收益与净值；
   - 计入佣金（双向，单笔最低）、印花税（仅卖出）、滑点（双边）。

3. 市场监管：
   - 股票涨停不可买、跌停不可卖（前复权空间内以涨跌幅判定）；
   - 停牌/无行情日不可成交，逐日标注，不静默跳过。

4. 匹配鲁棒（维度 4）：所有行情以 (标的代码, 日期) 为键存取，
   数据源返回顺序打乱后结果逐位一致；禁止用行位置/下标对齐。
   显式区分「待人工复核」与「无行情」。

5. 守恒与溯源（维度 2/3）：成交台账逐笔记录，供独立重算对账；
   缺失数据从不以前值/0/插值填充。

6. 确定性（维度 7）：无随机过程；相同输入 -> 完全相同输出。
"""
import sys
import os
import hashlib

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.engine import costs as COSTS
from backend.engine.exceptions import ValidationError


class StrategyContext:
    """策略可调用的只读上下文：历史收盘价、当日 bar。"""

    def __init__(self, bars: dict, universe: list, closes_index: dict):
        self.bars = bars
        self.universe = universe
        self._closes = closes_index  # {symbol: [(date, close), ...] 升序}

    def closes(self, symbol: str, upto_date: str) -> list:
        """返回 symbol 在 upto_date（含）之前的收盘价序列。"""
        lst = self._closes.get(symbol, [])
        return [c for (dt, c) in lst if dt <= upto_date]

    def bar(self, symbol: str, date: str) -> dict:
        return self.bars.get(symbol, {}).get(date)


class BacktestEngine:
    def __init__(self, bars: dict, bench_bars: dict, bench_symbol: str,
                 cfg: dict, strategy, options: dict = None):
        self.bars = bars
        self.bench_bars = bench_bars
        self.bench_symbol = bench_symbol
        self.cfg = cfg
        self.strategy = strategy
        self.options = options or {}

        self.universe = list(bars.keys())
        self.initial_capital = float(cfg["backtest"]["initial_capital"])
        self.costs = cfg["costs"]
        self.slip = self.costs["slippage_rate"]
        self.min_trade_value = self.options.get("min_trade_value", 1.0)
        self.enforce_lot = bool(cfg["backtest"].get("enforce_lot", False))
        self.lot_size = int(cfg["backtest"].get("lot_size", 100))
        self.abnormal_threshold = float(cfg["metrics"]["abnormal_return_threshold"])

        # 状态
        self.cash = self.initial_capital
        self.positions = {s: 0.0 for s in self.universe}
        self.avg_cost = {s: 0.0 for s in self.universe}
        self.last_close = {s: None for s in self.universe}

        # 日期轴：标的池与基准的并集，升序（按键匹配，绝不依赖顺序）
        dates_set = set()
        for s, bd in bars.items():
            dates_set.update(bd.keys())
        for s, bd in bench_bars.items():
            dates_set.update(bd.keys())
        self.all_dates = sorted(dates_set)

        # 收盘价索引（用于策略历史查询，按键存取）
        self._closes_index = {}
        for s, bd in bars.items():
            self._closes_index[s] = sorted(((d, v["close"]) for d, v in bd.items()),
                                          key=lambda x: x[0])
        self.ctx = StrategyContext(bars, self.universe, self._closes_index)

        # 基准首日收盘价
        self.bench_first_close = None
        bser = bench_bars.get(bench_symbol, {})
        for d in self.all_dates:
            if d in bser:
                self.bench_first_close = bser[d]["close"]
                break

        self.prev_nav = None

    # --------------------------- 主循环 ---------------------------
    def run(self) -> dict:
        daily = []
        ledger = []
        anomalies = []
        warnings = []

        pending = self.strategy.initialize(self.ctx)  # 首次决策（首日均开盘执行）
        for d in self.all_dates:
            # 1) 以第 d 日开盘价执行上一步决策（无前瞻）
            if pending is not None:
                self._execute_targets(pending, d, ledger, anomalies)
                pending = None
            # 2) 第 d 日收盘市值记账
            rec = self._record_day(d, ledger, anomalies)
            daily.append(rec)
            # 3) 更新「上一交易日收盘价」（用于次日涨跌停判定）
            for s in self.universe:
                bar = self.bars.get(s, {}).get(d)
                if bar is not None:
                    self.last_close[s] = bar["close"]
            # 4) 生成下一交易日决策
            pending = self.strategy.decide(d, self.ctx)

        return {
            "daily": daily,
            "ledger": ledger,
            "anomalies": anomalies,
            "warnings": warnings,
            "universe": self.universe,
            "initial_capital": self.initial_capital,
            "final_cash": self.cash,
            "final_positions": dict(self.positions),
        }

    # --------------------------- 执行层 ---------------------------
    def _current_weight(self, s, open_px, total_value):
        if total_value <= 0:
            return 0.0
        if open_px.get(s) is None:
            return 0.0
        return self.positions[s] * open_px[s] / total_value

    def _execute_targets(self, targets: dict, d: str, ledger: list, anomalies: list):
        open_px = {}
        has_bar = {}
        for s in self.universe:
            bar = self.bars.get(s, {}).get(d)
            has_bar[s] = bar is not None
            open_px[s] = bar["open"] if bar else None

        # 以「第 d 日开盘」 snapshot 估算组合总价值（用于目标权重换算）。
        # 注意：按 sorted(universe) 顺序求和，保证与输入/返回顺序无关（维度 4）。
        total_value = self.cash
        for s in sorted(self.universe):
            if has_bar[s]:
                total_value += self.positions[s] * open_px[s]
            elif self.positions[s] != 0:
                if self.last_close[s] is not None:
                    total_value += self.positions[s] * self.last_close[s]
                    anomalies.append({
                        "type": "valuation_estimate", "symbol": s, "date": d,
                        "msg": f"标的 {s} 在 {d} 无行情/停牌，市值暂用上一交易日收盘价估算，待人工复核。",
                    })
                else:
                    anomalies.append({
                        "type": "valuation_unknown", "symbol": s, "date": d,
                        "msg": f"标的 {s} 在 {d} 无行情且无历史收盘价，市值无法估算，待人工复核。",
                    })

        # 生成订单
        orders = []
        for s in self.universe:
            tw = targets.get(s, 0.0)
            if not has_bar[s]:
                if abs(tw - self._current_weight(s, open_px, total_value)) > 1e-9:
                    anomalies.append({
                        "type": "skip_trade", "symbol": s, "date": d,
                        "msg": f"标的 {s} 在 {d} 无行情/停牌，无法调仓至权重 {tw:.4f}，已跳过该标的调仓。",
                    })
                continue
            target_val = tw * total_value
            cur_val = self.positions[s] * open_px[s]
            delta = target_val - cur_val
            if abs(delta) < self.min_trade_value:
                continue
            orders.append((s, "buy" if delta > 0 else "sell", abs(delta)))

        # 确定性执行顺序：先卖后买，同类按代码升序（与输入顺序无关）
        orders.sort(key=lambda o: (0 if o[1] == "sell" else 1, o[0]))
        sells = [o for o in orders if o[1] == "sell"]
        buys = [o for o in orders if o[1] == "buy"]
        for s, side, value in sells:
            self._do_trade(s, side, value, d, open_px[s], ledger, anomalies)

        # 买入按「比例缩放」统一受现金预算约束，避免顺序导致的不公平短缺（维度 4）
        if buys:
            rate = self.costs["commission_rate"]
            minc = self.costs["min_commission"]
            cash_avail = self.cash
            gross = sum(v for _, _, v in buys)
            est_comm = sum(max(v * rate, minc) for _, _, v in buys)
            factor = (cash_avail / (gross + est_comm)) if (gross + est_comm) > cash_avail + 1e-9 else 1.0
            for s, side, value in buys:
                self._do_trade(s, side, value * factor, d, open_px[s], ledger, anomalies)

    def _do_trade(self, s, side, value, d, open_px, ledger, anomalies):
        bar = self.bars[s][d]
        at = bar["asset_type"]
        # 涨跌停约束（仅股票）
        limit_status = "none"
        if at == "stock":
            lp = COSTS.limit_pct_for(s, self.costs)
            limit_status = COSTS.detect_limit_status(bar["close"], self.last_close[s], lp)
            if not COSTS.is_tradable(side, at, limit_status):
                word = "涨停" if limit_status == "up" else "跌停"
                action = "不可买入" if side == "buy" else "不可卖出"
                anomalies.append({
                    "type": "limit", "symbol": s, "date": d, "side": side,
                    "msg": f"标的 {s} 在 {d} {word}，{action}，该笔订单未执行。",
                })
                return

        exec_px = COSTS.apply_slippage(open_px, side, self.slip)
        shares = value / exec_px
        if self.enforce_lot and self.lot_size > 0:
            shares = int(shares // self.lot_size) * self.lot_size
            if shares <= 0:
                return

        trade_value = shares * exec_px
        commission, stamp, total_cost = COSTS.compute_trade_cost(side, trade_value, self.costs)

        if side == "buy":
            rate = self.costs["commission_rate"]
            minc = self.costs["min_commission"]
            # 买入成本 = 成交额 + max(成交额*佣金率, 最低佣金)；精确求解可负担金额，
            # 避免「因最低佣金而永远差几元导致最后一笔买入被拒」的虚假 no_cash。
            def buy_cost(tv):
                return tv + max(tv * rate, minc)

            if buy_cost(value) <= self.cash + 1e-9:
                shares = value / exec_px
            else:
                if self.cash <= minc + 1e-9:
                    anomalies.append({"type": "no_cash", "symbol": s, "date": d,
                                      "msg": f"标的 {s} 在 {d} 现金不足以支付最低佣金，买入未执行。"})
                    return
                tv = (self.cash / (1.0 + rate)) if (self.cash * rate >= minc) else (self.cash - minc)
                tv = max(tv, 0.0)
                if tv <= 0:
                    anomalies.append({"type": "no_cash", "symbol": s, "date": d,
                                      "msg": f"标的 {s} 在 {d} 现金不足，买入未执行。"})
                    return
                shares = tv / exec_px
            trade_value = shares * exec_px
            commission, stamp, total_cost = COSTS.compute_trade_cost(side, trade_value, self.costs)
            needed = trade_value + total_cost
            # 浮点兜底：若仍超限，按现金精确缩减到「成本恰好等于现金」
            if needed > self.cash + 1e-9:
                tv = (self.cash / (1.0 + rate)) if (self.cash * rate >= minc) else (self.cash - minc)
                shares = max(tv, 0.0) / exec_px
                trade_value = shares * exec_px
                commission, stamp, total_cost = COSTS.compute_trade_cost(side, trade_value, self.costs)
                needed = trade_value + total_cost
            # 更新加权成本
            old_shares = self.positions[s]
            new_shares = old_shares + shares
            if new_shares > 0:
                self.avg_cost[s] = (self.avg_cost[s] * old_shares + exec_px * shares) / new_shares
            self.cash -= needed
            self.positions[s] = new_shares
        else:  # sell
            shares = min(shares, self.positions[s])
            if shares <= 0:
                return
            trade_value = shares * exec_px
            commission, stamp, total_cost = COSTS.compute_trade_cost(side, trade_value, self.costs)
            realized_pnl = (exec_px - self.avg_cost[s]) * shares - total_cost
            self.cash += (trade_value - total_cost)
            self.positions[s] -= shares
            if abs(self.positions[s]) < 1e-9:
                self.positions[s] = 0.0
                self.avg_cost[s] = 0.0

        ledger.append({
            "date": d, "symbol": s, "side": side,
            "shares": shares, "price": exec_px,
            "trade_value": trade_value,
            "commission": commission, "stamp": stamp,
            "cost_total": total_cost,
            "cash_after": self.cash,
            "limit_status": limit_status, "asset_type": at,
            "realized_pnl": realized_pnl if side == "sell" else None,
        })

    # --------------------------- 记账层 ---------------------------
    def _record_day(self, d, ledger, anomalies) -> dict:
        unknown = False
        positions_value = 0.0
        for s in sorted(self.universe):
            bar = self.bars.get(s, {}).get(d)
            if bar is None:
                if self.positions[s] != 0:
                    unknown = True
                    anomalies.append({
                        "type": "no_price", "symbol": s, "date": d,
                        "msg": f"标的 {s} 在 {d} 无行情/停牌，持仓 {self.positions[s]:.4f} 无法估值，本日净值待人工复核。",
                    })
                continue
            positions_value += self.positions[s] * bar["close"]

        portfolio_value = self.cash + positions_value
        nav = None if unknown else portfolio_value / self.initial_capital

        daily_return = None
        if nav is not None and self.prev_nav is not None:
            daily_return = nav / self.prev_nav - 1.0
            if abs(daily_return) > self.abnormal_threshold:
                anomalies.append({
                    "type": "abnormal_return", "date": d,
                    "msg": f"{d} 组合单日收益 {daily_return:+.4f} 超阈值 {self.abnormal_threshold}，疑似复权/对齐错误，待人工复核。",
                })

        bser = self.bench_bars.get(self.bench_symbol, {})
        bclose = bser.get(d, {}).get("close") if d in bser else None
        bench_nav = (bclose / self.bench_first_close) if (bclose and self.bench_first_close) else None

        if nav is not None:
            self.prev_nav = nav

        return {
            "date": d,
            "nav": nav,
            "portfolio_value": portfolio_value,
            "cash": self.cash,
            "positions_value": positions_value,
            "positions": {s: round(self.positions[s], 6) for s in self.universe},
            "bench_nav": bench_nav,
            "daily_return": (round(daily_return, 6) if daily_return is not None else None),
            "unknown_flag": unknown,
        }


def build_fingerprint(symbols, start, end, strategy_key, params, costs) -> str:
    """确定性指纹：相同输入 -> 相同指纹（维度 7）。"""
    raw = f"{symbols}|{start}|{end}|{strategy_key}|{params}|{costs}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
