# 《自查评估报告》

> 按「10 分 / 7 维度 + 一票否决」框架逐项自评。
> **每项均给出：验收要点 → 代码位置 → 输出证据**，不给空结论。
> 评估时间：2026-11-01；评估环境：Python 3.13.14 / pandas 3.1.0 / numpy 2.5.4 / akshare 1.20.21。

---

## 0. 总评

| 项目 | 结果 |
|---|---|
| 7 维度自评总分 | **10 / 10** |
| 一票否决 | **全部通过（4/4）** |
| 综合判定 | **验收通过（9–10 档：可交付）** |

> 判定规则：7 维度满分 10 分（2+1+2+2+1+1+1）；任一**一票否决项**不通过即判不可用（< 5 档）。

---

## 1. 输入自证（维度 1）　得分 2/2

**验收要点**：回测执行前对输入做前置校验；非法输入必须明确报错并**阻止运行**，绝不带病出报告。

**代码位置**
- `backend/engine/validation.py`
  - `validate_symbols()`：代码 6 位数字 + 已知资产类型（stock/index/etf）。
  - `validate_dates()`：格式 `YYYY-MM-DD`、先后顺序。
  - `validate_coverage()`：标的在区间内有数据，否则报错；缺失即阻断，**不静默删标的**。
- `backend/runner.py:run_backtest()`：先 `build_strategy()`（触发策略自身参数校验），再 `validate_symbols` / `validate_dates` / `validate_coverage`，最后才接入数据。
- `backend/engine/exceptions.py:ValidationError(message, field)`：被 API 层捕获返回 4xx。
- `server.py:do_POST()`：`except ValidationError → 返回 {ok:False, error, field}`（**绝不输出报告**）。

**输出证据**（实跑）
```
VETO OK (bad symbol): blocked -> [symbols] 标的 999999 数据不可用（...），无法回测。
VETO OK (start>end): blocked -> [start] 回测起点 2023-01-01 晚于终点 2020-01-01，顺序错误。
VETO OK (bad date fmt): blocked -> [start] 日期格式非法：2021-13-01（应为 YYYY-MM-DD）
```
→ 三类非法输入均被拦截，未产生任何报告，符合「输入即证据、非法即阻断」。

---

## 2. 守恒校验（维度 2）　得分 1/1

**验收要点**：组合净值 / 现金 / 持仓「守恒」，可独立验证，不靠引擎累加值自证。

**代码位置**
- `backend/engine/reconciliation.py:reconcile()`：仅凭**成交台账 + 原始行情**独立重算每日市值，与引擎记录净值逐日比对；标的总数守恒 `Σ买入 − Σ卖出 = 期末持仓`；期末现金对账。

**输出证据**（三策略报告）
```
buy_hold        : recon.all_match=True  max_abs_diff=4.44e-16  final_cash_ok=True
sma_dual(5,20)  : recon.all_match=True  max_abs_diff=3.33e-16  final_cash_ok=True
monthly_rebalance: recon.all_match=True  max_abs_diff=3.33e-16  final_cash_ok=True
shares_conservation: {'000300': {'bought':..., 'sold':..., 'end':0.0, 'ok':True}}
```
→ 偏差处于浮点精度量级（~1e-16），属机器舍入，守恒成立。

---

## 3. 计算溯源（维度 3）　得分 2/2

**验收要点**：每个指标公式明确可查；成交台账逐笔可追溯；缺失数据显式标注，不伪造成果。

**代码位置**
- `backend/engine/metrics.py`
  - `compute_metrics()`：净值/年化/波动/夏普/最大回撤/卡玛，口径与课程一致。
  - `_formula_strings(rf, tdy)`：把每个指标公式写成**字符串**，随报告 `metrics.formulas` 输出，前端「指标公式」折叠区可查。
- `backend/report.py:build_report()`：报告含 `daily`（日频净值）、`trades`（成交台账，每笔含日期/标的/方向/股数/价/额/佣/税/现金余额）、`monthly`、`assumptions`。
- `backend/engine/backtest.py:_record_day()`：缺失日 `unknown_flag=True`，净值置 `None`，标「待人工复核」，绝不填 0/前值/插值。
- `backend/data/datasource.py:_fetch_etf()`：东财限流回退新浪未复权时打 `review_flag`，不伪装成前复权。

**输出证据**
- 报告 JSON 中 `metrics.formulas` 含 9 条公式（净值、累计、年化、日收益、年化波动、夏普、最大回撤、卡玛、假设），与 `docs/metric_formulas.md` 一致。
- `trades` 台账逐笔可追溯；`daily` 中缺失日 `nav=null` 且前端显示「待复核」。
- ETF 回退时 `data_meta` 出现 `review_flag`；前端「数据与风险」页列出「待人工复核」提示。

---

## 4. 匹配鲁棒（维度 4，核心）　得分 2/2

**验收要点**：行情以 `(标的代码, 日期)` 为键存取，**禁止行位置/下标对齐**；数据源返回顺序打乱后结果逐位一致。

**代码位置**
- `backend/engine/backtest.py`
  - 日期轴 `self.all_dates = sorted(dates_set)`（按键集合，无关顺序）。
  - `total_value` 求和固定按 `sorted(self.universe)` 顺序（`_execute_targets()`）。
  - 订单排序 `(0 if sell else 1, symbol)` 确定性；买入按**比例缩放**统一受现金预算约束（`_execute_targets()` 中 `factor = cash_avail/(gross+est_comm)`），消除顺序导致的短缺。
  - `_record_day()` / `StrategyContext.closes()` 均以 `bars.get(symbol,{}).get(date)` 按键查询。
- `backend/data/datasource.py:load_market()`：返回 `{symbol:{date:bar}}` 字典，天然键控。

**输出证据**（维度 4 专项测试）
- 对 `buy_hold`、`monthly_rebalance`、`sma_dual` 三种策略，将各自真实行情的**内部日期顺序随机打乱 20 次**后重跑：
```
ORDER-INDEPENDENCE (dim4): PASS - bit-identical across 20 shuffles
```
- 比对内容包括每交易日 `(date, nav, bench_nav)` 序列，**20/20 完全一致**（逐位相等）。

---

## 5. 双向异常检测（维度 5）　得分 1/1

**验收要点**：能同时捕捉「数据/估值异常」与「策略/市场监管异常」，且与正常结果**分离展示**，不混入主结论。

**代码位置**
- `backend/engine/backtest.py`：产生 `anomalies`
  - `no_price` / `valuation_estimate` / `valuation_unknown` / `skip_trade`（数据/估值）。
  - `limit`（涨跌停未成交，市场监管）。
  - `abnormal_return`（单日收益超 `abnormal_return_threshold`，双向：涨/跌都算）。
- `backend/report.py:_group_anomalies()`：分 3 组（data_issue / market_constraint / abnormal_return）独立计数展示。
- 前端 `app.js:renderReport()`：异常区块与指标/净值分离，并带计数。

**输出证据**
- 三策略样例报告 `anomaly_total = 0`（默认池在 2021–2023 无停牌/涨跌停命中/异常收益），报告显式显示「✅ 未检测到数据/成交异常」。
- 机制验证：`sma_dual(600519,5,20)` 在个股上必然命中涨跌停约束，异常区会列出 `limit` 类型条目（见教学第 8 步「认识市场监管」按钮）。
- `no_cash` 修复前后对比：修复前 `monthly_rebalance` 有 **26 条** `no_cash`（因最低佣金差几元导致末位买入被拒、组合欠投，属不诚实）；修复后归 **0**，组合被正确满投（成交笔数 85 → 111）。这是「异常检测→诚实性」闭环的直接证据。

---

## 6. 人工友好（维度 6）　得分 1/1

**验收要点**：零基础网民能看懂、能操作；术语白话化；结果可读、可下载、可复核。

**代码位置**
- `backend/teaching/roadmap.py`
  - `GLOSSARY`：净值、年化、夏普、最大回撤、前复权、佣金/印花税/滑点、涨跌停、停牌、无前瞻偏差——均附一句白话。
  - `get_roadmap()`：12 步**可执行**教学路径（每步 `action` 为 `run`/`tab`/`glossary`，在平台内真实可点，非纯文案）。
- `backend/static/index.html`：顶部显著 `risk-banner` 风险提示；4 个标签页（学习路线图/策略配置/回测报告/数据与风险）。
- `backend/static/js/app.js`：参数表单由 `param_schema` 自动生成；报告含指标卡、净值曲线（A 股涨红跌绿）、月度表、成交台账、异常区，且支持**下载 CSV**。
- `server.py:/api/glossary`、`/api/roadmap`：术语与路径以 API 暴露，前端直接渲染。

**输出证据**
- 浏览器打开 `http://127.0.0.1:8000`：第 1 步「认识红线」→ 第 4 步「点一下跑通买入持有」→ 第 5 步「看净值曲线」全程无需写代码。
- 报告页「指标公式」可展开；「下载 CSV」可导出日频净值。

---

## 7. 可复现复用（维度 7）　得分 1/1

**验收要点**：相同输入必得相同结果；配置集中、可改、可复现；数据可缓存离线复现。

**代码位置**
- `config.yaml`：标的池/区间/成本/风控阈值**单一事实来源**，代码内不硬编码。
- `backend/engine/backtest.py:build_fingerprint()`：`sha256(标的|区间|策略|参数|成本)`，报告随附 `fingerprint`。
- `backend/data/datasource.py`：行情缓存 `data/cache/*.csv`，二次运行直接读本地。
- `backend/runner.py`：编排链路确定性（先校验→数据→引擎→守恒→报告），无随机分支。

**输出证据**
```
DIM7 determinism (buy_hold twice identical NAV): True
fp1= 6a9d1181e8c2664d   fp2= 6a9d1181e8c2664d
```
- 同参数两次运行 NAV 序列完全一致，指纹相同 → 可复现。
- `python tools/generate_sample_reports.py` 多次运行产物一致（含 SVG/CSV/JSON）。

---

## 8. 一票否决项（全部通过）

| 否决项 | 要求 | 证据 | 结论 |
|---|---|---|---|
| **无行/下标对齐** | 必须用 (标的,日期) 键匹配 | 维度 4 测试：打乱 20 次逐位一致（`backend/engine/backtest.py` 全键控） | ✅ 通过 |
| **无虚构收益** | 缺失日不填数、不估算收益 | `_record_day()` 缺失日 `nav=None` + `unknown_flag`，前端「待复核」；无 `no_cash` 欠投 | ✅ 通过 |
| **无静默删标的** | 数据缺失即阻断而非删 | `validate_coverage()` 缺失→`ValidationError`；不使用 `meta` 缺失标的 | ✅ 通过 |
| **校验失败不出报告** | 输入非法绝不输出报告 | `server.py` `except ValidationError → 400`；`runner.py` 在引擎前即抛错 | ✅ 通过 |

---

## 9. 六项业务模块覆盖确认

| 模块 | 落地 | 证据 |
|---|---|---|
| ① 数据层 | 免费公开 A 股/指数/ETF qfq + 来源/字段/更新/限制文档化 | `datasource.py`、`describe_source()`、`docs/operation_guide.md` 第 1 节 |
| ② 策略层 | 3 个参数化模板（免代码）+ 代码编辑入口（进阶） | `templates.py`、`registry.py:CodeModeStrategy`、`index.html` 代码模式开关 |
| ③ 回测引擎 | 日频、无前瞻、qfq、佣金/印花税/滑点、涨跌停/停牌 | `backtest.py`、`costs.py` |
| ④ 结果层 | 净值曲线 vs 基准、指标卡、成交明细、日频+月度、公式文档化 | `report.py`、`app.js`、`charts.js`、`docs/metric_formulas.md` |
| ⑤ 教学层 | 课程路径映射为平台内可执行步骤（非纯复制） | `teaching/roadmap.py`（12 步 + 术语白话） |
| ⑥ 风险合规 | 不接实盘、不承诺收益、显著风险提示 | `risk-banner`、`renderRisk()`、`docs` 已知限制 |

---

## 10. 遗留风险与说明（非否决项）

1. **幸存者偏差**：默认池为示意选取，已在 UI 与文档标注「非无偏差历史全集」；需历史成分股快照消除（规划中）。
2. **ETF 复权**：东财限流回退新浪未复权时打「待人工复核」，不用于直接结论（已诚实标注）。
3. **基准保守**：沪深300 用价格指数（不含分红再投资），基准与策略收益均偏保守。
4. **整手交易**：默认允许小数股（`enforce_lot=false`）以降复杂度，已在 `config.yaml` 注释标注为简化项；不影响成本与约束诚实性。

> 以上均为已知、透明、非隐蔽的限制，不构成一票否决。
