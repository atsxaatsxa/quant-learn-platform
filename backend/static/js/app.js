/* 量化学习平台前端逻辑（原生 JS，无框架依赖）。 */
(function () {
  "use strict";
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  const state = { config: null, strategies: null, roadmap: null, currentReport: null };

  // ---------------- 工具 ----------------
  async function getJSON(url) {
    const r = await fetch(url);
    return r.json();
  }
  async function postJSON(url, body) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return r.json();
  }
  function fmtPct(x) { return x == null ? "—" : (x * 100).toFixed(2) + "%"; }
  function fmtNum(x, d) { return x == null ? "—" : Number(x).toFixed(d == null ? 2 : d); }
  // A股惯例：涨红跌绿
  function signClass(x) { return x == null ? "" : (x >= 0 ? "pos" : "neg"); }

  // ---------------- 标签页 ----------------
  $$(".tab").forEach(btn => {
    btn.addEventListener("click", () => {
      $$(".tab").forEach(b => b.classList.remove("active"));
      $$(".tabpane").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      $("#tab-" + btn.dataset.tab).classList.add("active");
    });
  });
  function showTab(name) {
    $(`.tab[data-tab="${name}"]`).click();
  }

  // ---------------- 初始化 ----------------
  async function init() {
    state.config = await getJSON("/api/config");
    state.strategies = await getJSON("/api/strategies");
    const rm = await getJSON("/api/roadmap");
    state.roadmap = rm;
    renderConfigSelect();
    renderRoadmap(rm);
    renderRisk();
  }

  // ---------------- 教学路线图 ----------------
  function renderRoadmap(rm) {
    const box = $("#roadmap-list");
    box.innerHTML = "";
    rm.steps.forEach(step => {
      const div = document.createElement("div");
      div.className = "step";
      div.id = "step-" + step.id;
      let html = `<h3>第 ${step.id} 步 · ${step.title}</h3>`;
      html += `<div class="blurb">${step.blurb}</div>`;
      if (step.glossary_term) {
        const g = rm.glossary[step.glossary_term] || "";
        html += `<span class="gloss">📖 ${step.glossary_term}：${g}</span>`;
      }
      html += `<div class="actions"></div>`;
      div.innerHTML = html;
      const acts = div.querySelector(".actions");
      const a = step.action;
      if (a && a.type === "run") {
        const b = document.createElement("button");
        b.className = "run-btn";
        b.textContent = "▶ " + (a.caption || "运行");
        b.onclick = () => runFromAction(a, div);
        acts.appendChild(b);
      } else if (a && a.type === "tab") {
        const b = document.createElement("button");
        b.className = "run-btn";
        b.textContent = "前往：" + (a.target === "risk" ? "数据与风险" : a.target === "config" ? "策略配置" : "回测报告");
        b.onclick = () => showTab(a.target);
        acts.appendChild(b);
      }
      (step.extra_actions || []).forEach(ea => {
        const b = document.createElement("button");
        b.className = "run-btn";
        b.textContent = "▶ " + ea.caption;
        b.onclick = () => runFromAction({ type: "run", strategy_key: ea.strategy_key, params: ea.params, start: state.config.backtest.default_start, end: state.config.backtest.default_end }, div);
        acts.appendChild(b);
      });
      box.appendChild(div);
    });
    // 术语表
    const gb = $("#glossary-box");
    let gh = "<h3>📖 术语白话表</h3>";
    Object.keys(rm.glossary).forEach(k => {
      gh += `<div class="gloss-item"><b>${k}：</b>${rm.glossary[k]}</div>`;
    });
    gb.innerHTML = gh;
  }

  function runFromAction(a, stepDiv) {
    const req = {
      strategy_key: a.strategy_key,
      params: a.params || {},
      start: a.start || state.config.backtest.default_start,
      end: a.end || state.config.backtest.default_end,
    };
    runBacktest(req).then(() => {
      if (stepDiv) stepDiv.classList.add("done");
    });
  }

  // ---------------- 策略配置 ----------------
  function renderConfigSelect() {
    const sel = $("#strategy-select");
    sel.innerHTML = "";
    state.strategies.templates.forEach(t => {
      const o = document.createElement("option");
      o.value = t.key; o.textContent = t.name;
      sel.appendChild(o);
    });
    sel.onchange = renderParamForm;
    renderParamForm();
    // 日期
    $("#date-start").value = state.config.backtest.default_start;
    $("#date-end").value = state.config.backtest.default_end;
    // 代码模式
    $("#code-editor").value = state.strategies.sample_code;
    $("#code-mode-toggle").onchange = e => {
      $("#code-editor").style.display = e.target.checked ? "block" : "none";
      $("#param-form").style.display = e.target.checked ? "none" : "block";
    };
    $("#run-btn").onclick = runFromConfig;
  }

  function renderParamForm() {
    const key = $("#strategy-select").value;
    const t = state.strategies.templates.find(x => x.key === key);
    const box = $("#param-form");
    box.innerHTML = "";
    (t.param_schema || []).forEach(p => {
      const row = document.createElement("div");
      row.className = "param-row";
      const lab = document.createElement("label");
      lab.textContent = p.label;
      row.appendChild(lab);
      let input;
      if (p.type === "choice") {
        input = document.createElement("select");
        (p.options || []).forEach(o => {
          const oo = document.createElement("option");
          oo.value = o.value; oo.textContent = o.label; input.appendChild(oo);
        });
      } else if (p.type === "int" || p.type === "float") {
        input = document.createElement("input");
        input.type = "number";
        input.value = p.default;
        if (p.min != null) input.min = p.min;
        if (p.max != null) input.max = p.max;
        if (p.step != null) input.step = p.step;
      } else {
        input = document.createElement("input");
        input.type = "text"; input.value = p.default || "";
      }
      input.dataset.key = p.key;
      input.dataset.type = p.type;
      row.appendChild(input);
      if (p.help) {
        const h = document.createElement("div");
        h.style.cssText = "font-size:11.5px;color:#6b7280;margin-top:2px;";
        h.textContent = p.help;
        row.appendChild(h);
      }
      box.appendChild(row);
    });
  }

  function collectParams() {
    const params = {};
    $$("#param-form .param-row input, #param-form .param-row select").forEach(inp => {
      const k = inp.dataset.key, ty = inp.dataset.type;
      let v = inp.value;
      if (ty === "int") v = parseInt(v, 10);
      else if (ty === "float") v = parseFloat(v);
      params[k] = v;
    });
    return params;
  }

  function runFromConfig() {
    const useCode = $("#code-mode-toggle").checked;
    let req;
    if (useCode) {
      req = { strategy_key: "code", params: { code: $("#code-editor").value } };
    } else {
      const key = $("#strategy-select").value;
      const params = collectParams();
      req = { strategy_key: key, params };
      // SMA 单标的：把所选标的作为唯一标的池
      if (key === "sma_dual" && params.symbol) {
        req.symbols = [{ symbol: params.symbol, asset_type: params.asset_type || "stock" }];
      }
    }
    req.start = $("#date-start").value;
    req.end = $("#date-end").value;
    runBacktest(req);
  }

  // ---------------- 运行回测 ----------------
  async function runBacktest(req) {
    const status = $("#config-status");
    if (status) { status.textContent = "运行中…"; status.className = "status"; }
    $("#report-empty").style.display = "none";
    try {
      const res = await postJSON("/api/backtest", req);
      if (!res.ok) {
        if (status) { status.textContent = "⚠️ " + res.error; status.className = "status err"; }
        return;
      }
      state.currentReport = res.report;
      renderReport(res.report);
      showTab("report");
      if (status) { status.textContent = "✅ 回测完成"; status.className = "status ok"; }
    } catch (e) {
      if (status) { status.textContent = "⚠️ 请求失败：" + e; status.className = "status err"; }
    }
  }

  // ---------------- 报告渲染 ----------------
  function renderReport(r) {
    const c = $("#report-content");
    c.style.display = "block";
    const m = r.metrics;
    const a = r.assumptions;
    let h = "";

    // 元信息
    h += `<div class="card"><div class="meta-line">策略：<b>${r.meta.strategy_name}</b>
      <span class="pill">${r.meta.strategy_key}</span></div>`;
    h += `<div class="meta-line">区间：${r.meta.start} ~ ${r.meta.end} ｜ 初始资金：${Number(r.meta.initial_capital).toLocaleString()} 元 ｜ 标的：${r.meta.symbols.map(s => s.symbol).join(", ")}</div>`;
    h += `<div class="meta-line">确定性指纹（相同输入必得相同结果）：<code>${r.fingerprint}</code></div>`;
    (r.warnings || []).forEach(w => { h += `<div class="warn">⚠️ ${w}</div>`; });
    h += `</div>`;

    // 指标卡
    h += `<div class="section-title">核心指标</div><div class="metrics">`;
    const cards = [
      ["累计收益率", fmtPct(m.total_return), signClass(m.total_return)],
      ["年化收益率", fmtPct(m.annualized_return), signClass(m.annualized_return)],
      ["年化波动率", fmtPct(m.annualized_volatility), ""],
      ["夏普比率", fmtNum(m.sharpe, 3), (m.sharpe || 0) >= 0 ? "pos" : "neg"],
      ["最大回撤", fmtPct(m.max_drawdown), "neg"],
      ["卡玛比率", fmtNum(m.calmar, 3), ""],
      ["基准年化收益", fmtPct(m.benchmark_annualized_return), signClass(m.benchmark_annualized_return)],
      ["超额年化", fmtPct(m.excess_annualized_return), signClass(m.excess_annualized_return)],
      ["成交笔数", r.trade_stats.num_trades, ""],
      ["胜率(卖出)", r.trade_stats.win_rate == null ? "—" : fmtPct(r.trade_stats.win_rate), ""],
    ];
    cards.forEach(([k, v, cls]) => {
      h += `<div class="metric"><div class="k">${k}</div><div class="v ${cls}">${v}</div></div>`;
    });
    h += `</div>`;

    // 净值曲线
    h += `<div class="section-title">净值曲线（策略 vs 基准）</div><div class="chart-wrap"><div id="nav-chart"></div></div>`;

    // 守恒校验
    const rec = r.reconciliation;
    h += `<div class="section-title">守恒校验（维度2）与可复现</div><div class="card">`;
    h += `<div class="meta-line">逐日净值对账（独立用成交台账重算）：<span class="${rec.all_match ? "ok-badge" : "bad-badge"}">${rec.all_match ? "✅ 全部一致" : "❌ 存在不一致"}</span> 最大偏差 ${fmtNum(rec.max_abs_diff, 12)}</div>`;
    h += `<div class="meta-line">期末现金对账：<span class="${rec.final_cash_ok ? "ok-badge" : "bad-badge"}">${rec.final_cash_ok ? "✅ 一致" : "❌ 不一致"}</span></div>`;
    const sc = rec.shares_conservation;
    const scOk = Object.values(sc).every(v => v.ok);
    h += `<div class="meta-line">标的总数守恒（买入-卖出=期末）：<span class="${scOk ? "ok-badge" : "bad-badge"}">${scOk ? "✅ 全部守恒" : "❌ 异常"}</span></div>`;
    h += `</div>`;

    // 假设与成本
    h += `<div class="section-title">回测假设与成本（指标口径）</div><div class="card">`;
    h += `<div class="meta-line">前复权：<b>${a.adjust}</b> ｜ 无风险利率：${fmtPct(a.risk_free_rate)} ｜ 年交易日：${a.trading_days_per_year}</div>`;
    h += `<div class="meta-line">佣金：${fmtPct(a.commission_rate)}（单笔最低 ${a.min_commission} 元）｜ 印花税（仅卖出）：${fmtPct(a.stamp_tax_rate)} ｜ 滑点：${fmtPct(a.slippage_rate)}（双边）</div>`;
    h += `<div class="meta-line">成交规则：<b>${a.execution_rule}</b></div>`;
    if (m.formulas) {
      h += `<details><summary>指标公式</summary><ul style="font-size:12.5px">`;
      Object.keys(m.formulas).forEach(k => { h += `<li><b>${k}：</b>${m.formulas[k]}</li>`; });
      h += `</ul></details>`;
    }
    h += `</div>`;

    // 月度汇总
    h += `<div class="section-title">月度汇总</div><div class="chart-wrap"><div id="monthly-chart"></div></div>`;
    h += `<div class="scroll"><table><thead><tr><th class="l">月份</th><th>月收益</th><th>月末净值</th><th>月内最大回撤</th><th>基准月收益</th><th>交易日</th></tr></thead><tbody>`;
    r.monthly.forEach(mo => {
      h += `<tr><td class="l">${mo.month}</td><td class="${signClass(mo.month_return)}">${fmtPct(mo.month_return)}</td><td>${fmtNum(mo.month_end_nav, 4)}</td><td class="neg">${fmtPct(mo.month_max_drawdown)}</td><td class="${signClass(mo.bench_month_return)}">${fmtPct(mo.bench_month_return)}</td><td>${mo.trading_days}</td></tr>`;
    });
    h += `</tbody></table></div>`;

    // 异常区块
    h += `<div class="section-title">异常检测（维度5/6：与正常结果分离展示）</div>`;
    Object.keys(r.anomalies).forEach(k => {
      const grp = r.anomalies[k];
      if (!grp.count) return;
      h += `<div class="anom-group"><b>${grp.label}（${grp.count} 条）</b>`;
      grp.items.slice(0, 12).forEach(it => { h += `<div>· ${it.msg}</div>`; });
      if (grp.count > 12) h += `<div>· …共 ${grp.count} 条</div>`;
      h += `</div>`;
    });
    if (Object.values(r.anomalies).every(g => g.count === 0)) {
      h += `<div class="anom-group" style="background:#f0fdf4;border-color:#bbf7d0;color:#166534"><b>✅ 未检测到数据/成交异常</b></div>`;
    }

    // 成交明细
    h += `<div class="section-title">成交明细台账（每笔可追溯）</div><div class="scroll"><table><thead><tr><th class="l">日期</th><th class="l">标的</th><th class="l">方向</th><th>股数</th><th>成交价</th><th>成交额</th><th>佣金</th><th>印花税</th><th>现金余额</th></tr></thead><tbody>`;
    r.trades.forEach(t => {
      const side = t.side === "buy" ? "买入" : "卖出";
      h += `<tr><td class="l">${t.date}</td><td class="l">${t.symbol}</td><td class="l">${side}</td><td>${fmtNum(t.shares, 2)}</td><td>${fmtNum(t.price, 3)}</td><td>${fmtNum(t.trade_value, 2)}</td><td>${fmtNum(t.commission, 2)}</td><td>${fmtNum(t.stamp, 2)}</td><td>${fmtNum(t.cash_after, 2)}</td></tr>`;
    });
    h += `</tbody></table></div>`;

    // 日频净值明细
    h += `<div class="section-title">日频净值明细（${r.daily.length} 行）<button id="dl-csv" class="run-btn" style="margin-left:10px">⬇ 下载CSV</button></div><div class="scroll"><table><thead><tr><th class="l">日期</th><th>策略净值</th><th>基准净值</th><th>日收益</th><th>现金</th><th>持仓市值</th></tr></thead><tbody>`;
    r.daily.forEach(d => {
      h += `<tr><td class="l">${d.date}</td><td>${d.nav == null ? "待复核" : fmtNum(d.nav, 4)}</td><td>${d.bench_nav == null ? "—" : fmtNum(d.bench_nav, 4)}</td><td class="${signClass(d.daily_return)}">${d.daily_return == null ? "—" : fmtPct(d.daily_return)}</td><td>${fmtNum(d.cash, 2)}</td><td>${fmtNum(d.positions_value, 2)}</td></tr>`;
    });
    h += `</tbody></table></div>`;

    c.innerHTML = h;

    // 图表
    QB.chart.nav($("#nav-chart"), r.daily);
    QB.chart.monthly($("#monthly-chart"), r.monthly);
    $("#dl-csv").onclick = () => downloadCSV(r);
  }

  function downloadCSV(r) {
    let csv = "date,nav,bench_nav,daily_return,cash,positions_value\n";
    r.daily.forEach(d => {
      csv += `${d.date},${d.nav == null ? "" : d.nav},${d.bench_nav == null ? "" : d.bench_nav},${d.daily_return == null ? "" : d.daily_return},${d.cash},${d.positions_value}\n`;
    });
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `nav_${r.meta.strategy_key}_${r.meta.start}_${r.meta.end}.csv`;
    a.click();
  }

  // ---------------- 数据与风险 ----------------
  function renderRisk() {
    const box = $("#risk-content");
    const cfg = state.config;
    let h = `<h2>④ 数据与风险 / 已知限制与规划</h2>`;
    h += `<div class="warn">⚠️ 本平台仅用于学习研究，所有结果为历史回测模拟，<b>不构成投资建议，不承诺收益</b>。未接入实盘交易。</div>`;
    h += `<div class="section-title">数据源（模块1）</div><div class="card">`;
    const si = cfg.source_info;
    h += `<div class="meta-line"><b>个股：</b>${si.stock}</div>`;
    h += `<div class="meta-line"><b>指数：</b>${si.index}</div>`;
    h += `<div class="meta-line"><b>ETF：</b>${si.etf}</div>`;
    h += `<div class="meta-line"><b>复权：</b>${si.adjust} ｜ <b>字段：</b>${si.fields.join(", ")}</div>`;
    h += `<div class="meta-line"><b>更新机制：</b>${si.update_mechanism}</div>`;
    h += `<div class="meta-line"><b>已知限制：</b></div><ul style="font-size:12.5px;margin:4px 0">`;
    (si.known_limits || []).forEach(l => h += `<li>${l}</li>`);
    h += `</ul></div>`;

    h += `<div class="section-title">已知限制</div><div class="card"><ul style="font-size:13px;margin:0">`;
    h += `<li>默认交易池为<b>示意性选取</b>（茅台/平安/招行），<b>非无幸存者偏差的历史全集</b>；专业研究需使用历史成分股快照。</li>`;
    h += `<li>指数使用<b>价格指数</b>，未含分红再投资（保守口径，收益略偏低）。</li>`;
    h += `<li>ETF 前复权依赖东方财富，限流时回退新浪未复权并标注「待人工复核」，不会伪装成前复权。</li>`;
    h += `<li>默认聚焦「新手全链路跑通」，因子研究、模拟交易、蒙特卡洛模拟等标记为 <b>规划中</b>。</li>`;
    h += `</ul></div>`;

    h += `<div class="section-title">规划中（不影响核心链路）</div><div class="card"><div class="meta-line">因子研究框架 ｜ 模拟交易 ｜ 多标的轮动 ｜ 蒙特卡洛模拟（课程第17讲）｜ 历史成分股快照（消除幸存者偏差）｜ 交易分钟级监控</div></div>`;
    box.innerHTML = h;
  }

  init().catch(e => {
    document.body.insertAdjacentHTML("afterbegin", `<div class="warn">初始化失败：${e}。请确认服务已启动（python server.py）。</div>`);
  });
})();
