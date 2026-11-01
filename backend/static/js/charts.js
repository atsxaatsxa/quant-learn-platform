/* 纯前端 SVG 图表（无外部依赖，离线可用）。A股惯例：涨=红，跌=绿。 */
window.QB = window.QB || {};
QB.chart = (function () {
  const BLUE = "#2563eb", ORANGE = "#ea580c", RED = "#dc2626", GREEN = "#16a34a", GRID = "#eceff3";

  function esc(s) { return String(s); }

  // 净值曲线：策略 vs 基准
  function nav(svg, daily) {
    const W = 960, H = 360, padL = 52, padR = 16, padT = 18, padB = 30;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const N = daily.length;
    const strat = [], bench = [];
    daily.forEach((r, i) => {
      if (r.nav != null) strat.push([i, r.nav]);
      if (r.bench_nav != null) bench.push([i, r.bench_nav]);
    });
    let vals = strat.concat(bench).map(p => p[1]);
    vals.push(1.0);
    let minV = Math.min(...vals), maxV = Math.max(...vals);
    if (minV === maxV) { minV -= 0.05; maxV += 0.05; }
    const xAt = i => padL + (N <= 1 ? 0 : (i / (N - 1)) * plotW);
    const yAt = v => padT + (maxV - v) / (maxV - minV) * plotH;

    let g = `<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet" font-family="sans-serif">`;
    // 网格 + Y 轴刻度
    const ticks = 4;
    for (let t = 0; t <= ticks; t++) {
      const v = minV + (maxV - minV) * t / ticks;
      const y = yAt(v);
      g += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="${GRID}" />`;
      g += `<text x="${padL - 6}" y="${y + 4}" text-anchor="end" font-size="11" fill="#6b7280">${v.toFixed(2)}</text>`;
    }
    // 净值=1.0 参考线
    const y1 = yAt(1.0);
    g += `<line x1="${padL}" y1="${y1}" x2="${W - padR}" y2="${y1}" stroke="#9ca3af" stroke-dasharray="4 4" />`;
    // X 轴首末标签
    g += `<text x="${padL}" y="${H - 10}" font-size="11" fill="#6b7280">${daily[0].date}</text>`;
    g += `<text x="${W - padR}" y="${H - 10}" text-anchor="end" font-size="11" fill="#6b7280">${daily[N - 1].date}</text>`;
    // 折线
    function path(arr, color) {
      if (!arr.length) return "";
      let d = "M" + arr.map(p => `${xAt(p[0]).toFixed(1)} ${yAt(p[1]).toFixed(1)}`).join(" L");
      return `<path d="${d}" fill="none" stroke="${color}" stroke-width="1.8" />`;
    }
    g += path(bench, ORANGE);
    g += path(strat, BLUE);
    // 图例
    g += `<rect x="${W - 230}" y="${padT}" width="12" height="12" fill="${BLUE}"/><text x="${W - 212}" y="${padT + 10}" font-size="12">策略净值</text>`;
    g += `<rect x="${W - 130}" y="${padT}" width="12" height="12" fill="${ORANGE}"/><text x="${W - 112}" y="${padT + 10}" font-size="12">基准(沪深300)</text>`;
    g += `</svg>`;
    svg.innerHTML = g;
  }

  // 月度收益柱状图
  function monthly(svg, monthly) {
    const W = 960, H = 220, padL = 44, padR = 12, padT = 16, padB = 28;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const n = monthly.length || 1;
    const rets = monthly.map(m => m.month_return == null ? 0 : m.month_return);
    let maxA = Math.max(0.001, ...rets.map(Math.abs));
    const y0 = padT + plotH / 2;
    const yAt = v => y0 - (v / maxA) * (plotH / 2);
    const bw = plotW / n * 0.7;
    let g = `<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet" font-family="sans-serif">`;
    g += `<line x1="${padL}" y1="${y0}" x2="${W - padR}" y2="${y0}" stroke="#9ca3af" />`;
    g += `<text x="${padL - 6}" y="${y0 + 4}" text-anchor="end" font-size="11" fill="#6b7280">0</text>`;
    monthly.forEach((m, i) => {
      const x = padL + (i + 0.5) * (plotW / n) - bw / 2;
      const v = m.month_return == null ? 0 : m.month_return;
      const y = yAt(v);
      const h = Math.abs(y - y0);
      const color = v >= 0 ? RED : GREEN;
      g += `<rect x="${x.toFixed(1)}" y="${Math.min(y, y0).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1, h).toFixed(1)}" fill="${color}" opacity="0.85"/>`;
      if (i % 3 === 0) g += `<text x="${(x + bw / 2).toFixed(1)}" y="${H - 10}" text-anchor="middle" font-size="9" fill="#6b7280">${m.month}</text>`;
    });
    g += `</svg>`;
    svg.innerHTML = g;
  }

  return { nav, monthly };
})();
