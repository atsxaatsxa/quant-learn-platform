# 《运行与验收说明》

> 配套交付物 ④。说明：数据源配置、如何复现回测结果、已知限制与未来规划。
> 适用对象：验收方 / 想自己跑一遍的开发者。

---

## 1. 数据源配置

所有数据配置集中在 **`config.yaml`**（单一事实来源，代码内不散落硬编码）。

### 1.1 数据源与优先级

| 资产类型 | 接口（akshare） | 复权方式 | 备注 |
|---|---|---|---|
| A 股个股 | `stock_zh_a_daily`（新浪源） | 前复权 `qfq` | 稳定、不易被限流 |
| 指数（如沪深300） | `stock_zh_a_daily`（新浪源） | 不调整（价格指数） | 不含分红再投资（保守口径） |
| ETF | 主用 `fund_etf_hist_em`（东方财富，qfq） | 前复权 `qfq` | 限流时回退 `fund_etf_hist_sina`（未复权）并标注「待人工复核」 |

取舍依据（为什么这么选）：
- **用 qfq（前复权）**：让历史与现在价格可比，直接算收益才不会出错（避免「用不复权价直接算历史收益」的常见坑）。
- **新浪为主、东财为回退**：新浪源对个股/指数基本不限流；东财 ETF 前复权有限流风险，命中即快速失败回退，绝不做重试轰炸。

对应代码：`backend/data/datasource.py`
- `load_market()` / `load_benchmark()`：统一入口，返回 `{symbol: {date: bar}}` 与 `meta`。
- `_dispatch_fetch()`：按 `asset_type` 分发到 `_fetch_stock` / `_fetch_index` / `_fetch_etf`。
- `_fetch_etf()`：东财失败 → 回退新浪未复权，并打 `review_flag`（**不静默伪装**）。
- `describe_source()`：返回给前端/文档的数据源说明（含字段、更新机制、已知限制）。

### 1.2 可配置项（改 `config.yaml` 即可，无需改代码）

```yaml
data:
  source_priority: [sina, em]
  cache_dir: data/cache          # 缓存 CSV，便于人工复核
  adjust: qfq                    # 前复权
  em_rate_limit_cooldown_sec: 60 # 东财限流冷却
  em_max_retries: 3

universe:
  default_symbols: [...]         # 默认交易池
  benchmark: { symbol: "000300", ... }
  etf_example: { symbol: "510300", ... }

backtest:
  initial_capital: 1000000.0
  default_start: "2021-01-01"
  default_end: "2023-12-31"

costs:
  commission_rate: 0.0003        # 万3
  min_commission: 5.0            # 单笔最低佣金
  stamp_tax_rate: 0.0005         # 印花税（仅卖出）
  slippage_rate: 0.001           # 滑点（双边）

metrics:
  risk_free_rate: 0.02           # 无风险利率（取正，拉低夏普，保守）
  trading_days_per_year: 252
  abnormal_return_threshold: 0.20 # 单日收益超此值标记待复核
```

### 1.3 缓存与更新

- 首次运行 / 缓存缺失时联网抓取，落地为 `data/cache/<asset_type>_<symbol>_<adjust>.csv`。
- 再次运行直接读缓存，**可离线复现**。
- 更新数据：`python tools/init_data.py --refresh`。

---

## 2. 如何复现回测结果

### 2.1 一键生成样例报告（交付物 ②/③）

```bash
pip install -r requirements.txt
python tools/init_data.py
python server.py &                 # 可选：启动 Web UI
python tools/generate_sample_reports.py
```

产物在 `outputs/`：

| 文件 | 内容 |
|---|---|
| `buy_hold_report.json` 等 | 三个策略完整报告 |
| `*_daily_nav.csv` | 日频净值明细 |
| `*_monthly.csv` | 月度汇总 |
| `*_nav_curve.svg` | 净值曲线（策略 vs 基准） |
| `sample_backtest_report.md` | 三策略同区间对比汇总 |

### 2.2 复现的确定性保证（维度 7）

- 引擎**无随机过程**；相同输入 → 完全相同输出。
- 每次运行附带 **确定性指纹** `fingerprint = sha256(标的|区间|策略|参数|成本)`（见 `backend/engine/backtest.py:build_fingerprint`）。
- 样例报告里相同参数两次运行指纹一致（已验证：`6a9d1181e8c2664d`）。

### 2.3 通过 Web UI 复现

启动 `python server.py` → 打开 `http://127.0.0.1:8000` →
「① 学习路线图」逐步点击，或「② 策略配置」选模板填参数运行。
后端 POST `/api/backtest` 返回与离线脚本**完全同构**的报告 JSON。

---

## 3. 验收要点（与自查报告对应）

| 验收维度 | 验证方式 | 结果 |
|---|---|---|
| 输入自证（维度1） | 非法标的/日期/顺序 → `ValidationError` 拦截，绝不带病出报告 | ✅ 见 `docs/self_check_report.md` |
| 守恒校验（维度2） | 独立用成交台账重算净值，逐日比对 | ✅ 偏差 ≤ 3.3e-16 |
| 计算溯源（维度3） | 指标公式显式字符串化，台账每笔可追溯 | ✅ |
| 匹配鲁棒（维度4） | 数据源返回顺序打乱 20 次，NAV 逐位一致 | ✅ |
| 双向异常检测（维度5） | 异常分组展示（数据/监管/异常收益） | ✅ |
| 人工友好（维度6） | 术语白话表 + 报告可读 + 下载 CSV | ✅ |
| 可复现复用（维度7） | config 单一来源 + 指纹 + 缓存 | ✅ |
| 一票否决 | 无行位置对齐 / 无虚构收益 / 无静默删标的 / 校验失败不出报告 | ✅ 全部满足 |

---

## 4. 已知限制（透明标注）

1. **幸存者偏差**：默认池为示意选取（茅台/平安/招行），非无偏差历史全集。已在 UI「数据与风险」页与代码注释标注。
2. **基准保守**：沪深300 用价格指数，未计入分红再投资；因此基准收益略低于全收益指数。
3. **ETF 复权风险**：东财限流回退新浪未复权时，打 `review_flag` 提示「待人工复核」，不用于直接收益结论。
4. **整手交易**：默认 `enforce_lot: false`（允许小数股）以降低复杂度，已在 `config.yaml` 注释标注为简化项；不影响成本与约束诚实性。
5. **频率**：聚焦日频回测（MVP 范围）；分钟级为「规划中」。
6. **涨跌停**：仅对**股票**施加涨停不可买/跌停不可卖；指数/ETF 不施加（已在 `costs.py`/`docs` 标注为简化）。

---

## 5. 未来规划（不影响核心链路，已在 UI 标「规划中」）

- 历史成分股快照（消除幸存者偏差）
- 因子研究框架（多因子选股）
- 模拟交易 / 纸上交易沙盒
- 蒙特卡洛模拟（课程第 17 讲）
- 多标的轮动回测
- 分钟级行情与更细成本模型

---

## 6. 故障排查

| 现象 | 排查 |
|---|---|
| 启动后页面打不开 | 确认 `python server.py` 已运行，浏览器访问 `http://127.0.0.1:8000` |
| 回测报「数据不可用」 | 先 `python tools/init_data.py` 初始化；检查 `config.yaml` 中标的代码 |
| ETF 报告出现「待人工复核」 | 东方财富限流，已回退新浪未复权；可稍后 `--refresh` 重试 |
| 想换区间/标的 | 改 `config.yaml` 的 `backtest` / `universe`，或 UI 内改日期 |
