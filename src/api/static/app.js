/**
 * Polymarket News Bot — Trading Terminal Dashboard
 *
 * Connects via WebSocket for real-time updates.
 * Falls back to polling /api/state every 10s on WS failure.
 */

'use strict';

// ── State ──────────────────────────────────────────────────────────────────

const state = {
  portfolio:  null,
  analyses:   {},   // market_id -> analysis object
  events:     [],
  news:       [],
  pnlHistory: [],
  startedAt:  null,
  connected:  false,
  hasData:    false, // tracks whether we've received market analysis data
};

// ── All 8 signal definitions ───────────────────────────────────────────────

const ALL_SIGNALS = [
  { key: 'microstructure_vpin',     label: 'VPIN',              icon: 'V', color: '#818cf8', desc: 'Informed trading detection via volume-synchronized probability' },
  { key: 'microstructure_spread',   label: 'Spread/Depth',      icon: 'S', color: '#a78bfa', desc: 'Orderbook depth imbalance and bid-ask spread analysis' },
  { key: 'cross_market',            label: 'Cross-Market',      icon: 'X', color: '#e5b95e', desc: 'Arbitrage signal from Kalshi, Metaculus, Manifold' },
  { key: 'news_rss',               label: 'News (RSS)',         icon: 'N', color: '#34d399', desc: 'TF-IDF relevance + sentiment from 15 RSS feeds' },
  { key: 'news_gdelt',             label: 'News (GDELT)',       icon: 'G', color: '#5eead4', desc: 'GDELT GKG 2.0 tone scoring from 100+ global sources' },
  { key: 'llm_decomposition',      label: 'LLM Forecaster',    icon: 'L', color: '#f472b6', desc: 'Superforecaster decomposition via Groq/Gemini/Ollama' },
  { key: 'wikipedia_velocity',     label: 'Wikipedia',          icon: 'W', color: '#e8915a', desc: 'Edit velocity spike detection (5-15 min pre-news)' },
  { key: 'reddit_social',          label: 'Reddit',             icon: 'R', color: '#f47067', desc: 'Social sentiment from r/PredictionMarkets + r/worldnews' },
];

// Human-readable signal source names
const SOURCE_LABELS = {};
ALL_SIGNALS.forEach(s => { SOURCE_LABELS[s.key] = s.label; });

function sourceLabel(raw) {
  return SOURCE_LABELS[raw] || raw.replace(/_/g, ' ');
}

// ── Charts ─────────────────────────────────────────────────────────────────

let pnlChart = null;
let radarChart = null;
let calibrationChart = null;

function initChart() {
  const ctx = document.getElementById('pnl-chart').getContext('2d');
  pnlChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: 'P&L %',
        data: [],
        borderColor: '#34d399',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.4,
        fill: {
          target: 'origin',
          above: 'rgba(52,211,153,0.08)',
          below: 'rgba(244,112,103,0.08)',
        },
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          enabled: true,
          backgroundColor: '#16181d',
          borderColor: '#3a3d47',
          borderWidth: 1,
          titleColor: '#5c5f6a',
          bodyColor: '#e8e9ec',
          titleFont: { family: 'JetBrains Mono, monospace', size: 9 },
          bodyFont: { family: 'JetBrains Mono, monospace', size: 11 },
          callbacks: {
            label: ctx => ' ' + (ctx.raw >= 0 ? '+' : '') + ctx.raw.toFixed(2) + '%',
          },
        },
      },
      scales: {
        x: { display: false },
        y: {
          grid: { color: '#2a2d35' },
          ticks: {
            color: '#5c5f6a',
            font: { family: 'JetBrains Mono, monospace', size: 10 },
            callback: v => v.toFixed(1) + '%',
          },
          border: { display: false },
        },
      },
    },
  });
}

function initRadarChart() {
  const ctx = document.getElementById('radar-chart').getContext('2d');
  radarChart = new Chart(ctx, {
    type: 'radar',
    data: {
      labels: ALL_SIGNALS.map(s => s.label),
      datasets: [{
        label: 'Signal Strength',
        data: Array(8).fill(0),
        borderColor: '#818cf8',
        borderWidth: 2,
        backgroundColor: 'rgba(129,140,248,0.08)',
        pointRadius: 4,
        pointBackgroundColor: ALL_SIGNALS.map(s => s.color),
        pointBorderColor: ALL_SIGNALS.map(s => s.color),
        pointHoverRadius: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#16181d',
          borderColor: '#3a3d47',
          borderWidth: 1,
          bodyColor: '#e8e9ec',
          bodyFont: { family: 'JetBrains Mono, monospace', size: 11 },
          callbacks: {
            label: ctx => {
              const val = ctx.raw;
              const dir = val > 0 ? 'YES' : val < 0 ? 'NO' : 'neutral';
              return ` ${dir} (${val > 0 ? '+' : ''}${val.toFixed(2)})`;
            },
          },
        },
      },
      scales: {
        r: {
          beginAtZero: false,
          min: -1,
          max: 1,
          ticks: {
            stepSize: 0.5,
            color: '#5c5f6a',
            font: { family: 'JetBrains Mono, monospace', size: 9 },
            backdropColor: 'transparent',
          },
          grid: { color: '#2a2d35' },
          angleLines: { color: '#2a2d35' },
          pointLabels: {
            color: ALL_SIGNALS.map(s => s.color),
            font: { family: 'Inter, sans-serif', size: 10, weight: '600' },
          },
        },
      },
    },
  });
}

function initCalibrationChart() {
  const ctx = document.getElementById('calibration-chart');
  if (!ctx) return;

  calibrationChart = new Chart(ctx.getContext('2d'), {
    type: 'bar',
    data: {
      labels: [],
      datasets: [
        {
          label: 'Predicted',
          data: [],
          backgroundColor: 'rgba(129,140,248,0.25)',
          borderColor: '#818cf8',
          borderWidth: 1.5,
          borderRadius: 3,
          barPercentage: 0.4,
          categoryPercentage: 0.8,
        },
        {
          label: 'Actual',
          data: [],
          backgroundColor: 'rgba(52,211,153,0.25)',
          borderColor: '#34d399',
          borderWidth: 1.5,
          borderRadius: 3,
          barPercentage: 0.4,
          categoryPercentage: 0.8,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 400 },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: {
            color: '#5c5f6a',
            font: { family: 'Inter, sans-serif', size: 10 },
            boxWidth: 12,
            padding: 12,
          },
        },
        tooltip: {
          backgroundColor: '#16181d',
          borderColor: '#3a3d47',
          borderWidth: 1,
          bodyColor: '#e8e9ec',
          bodyFont: { family: 'JetBrains Mono, monospace', size: 11 },
          callbacks: {
            label: ctx => ' ' + ctx.dataset.label + ': ' + (ctx.raw * 100).toFixed(0) + '%',
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            color: '#5c5f6a',
            font: { family: 'Inter, sans-serif', size: 10 },
          },
          border: { display: false },
        },
        y: {
          min: 0,
          max: 1,
          grid: { color: '#2a2d35' },
          ticks: {
            color: '#5c5f6a',
            font: { family: 'JetBrains Mono, monospace', size: 10 },
            callback: v => (v * 100).toFixed(0) + '%',
            stepSize: 0.25,
          },
          border: { display: false },
        },
      },
    },
  });

  // Fetch calibration data
  fetch('/api/calibration')
    .then(r => r.json())
    .then(data => {
      if (!calibrationChart || !data.length) return;
      calibrationChart.data.labels = data.map(d => d.bucket);
      calibrationChart.data.datasets[0].data = data.map(d => d.predicted);
      calibrationChart.data.datasets[1].data = data.map(d => d.actual);
      calibrationChart.update();
    })
    .catch(() => {});
}

function updateChart(history) {
  if (!pnlChart || !history.length) return;
  pnlChart.data.labels = history.map(p => {
    const d = new Date(p.ts * 1000);
    return d.getHours() + ':' + String(d.getMinutes()).padStart(2, '0');
  });
  pnlChart.data.datasets[0].data = history.map(p => p.pnl_pct);
  const vals = pnlChart.data.datasets[0].data;
  const last = vals.length ? vals[vals.length - 1] : 0;
  pnlChart.data.datasets[0].borderColor = last < 0 ? '#f47067' : '#34d399';
  pnlChart.update('none');
}

function updateRadarChart(signals) {
  if (!radarChart) return;

  // Map signal data to radar values: log(LR) clamped to [-1, 1]
  const values = ALL_SIGNALS.map(def => {
    const sig = signals.find(s => s.source === def.key);
    if (!sig) return 0;
    const lr = sig.eff_lr || sig.lr || 1;
    return Math.max(-1, Math.min(1, Math.log(lr) * sig.confidence));
  });

  radarChart.data.datasets[0].data = values;

  // Color based on net direction
  const netDirection = values.reduce((a, b) => a + b, 0);
  radarChart.data.datasets[0].borderColor = netDirection > 0 ? '#34d399' : netDirection < 0 ? '#f47067' : '#818cf8';
  radarChart.data.datasets[0].backgroundColor = netDirection > 0
    ? 'rgba(52,211,153,0.10)'
    : netDirection < 0 ? 'rgba(244,112,103,0.10)' : 'rgba(129,140,248,0.08)';
  radarChart.update('none');
}

// ── Formatting helpers ─────────────────────────────────────────────────────

function fmtPct(v, decimals = 2) {
  if (v == null) return '&mdash;';
  const s = (v >= 0 ? '+' : '') + v.toFixed(decimals) + '%';
  return `<span class="${v >= 0 ? 'pos' : 'neg'}">${s}</span>`;
}

function fmtUsd(v) {
  if (v == null) return '&mdash;';
  return '$' + v.toFixed(2);
}

function probColor(v) {
  if (v >= 0.6) return 'meter-fill-hi';
  if (v >= 0.35) return 'meter-fill-mid';
  return 'meter-fill-lo';
}

function fmtProb(v) {
  if (v == null) return '&mdash;';
  const pct = (v * 100).toFixed(1);
  const fill = Math.round(v * 100);
  const cls = probColor(v);
  return `<span class="prob-meter">
    <span>${pct}%</span>
    <span class="meter-track"><span class="meter-fill ${cls}" style="width:${fill}%"></span></span>
  </span>`;
}

function fmtEdge(v) {
  if (v == null) return '&mdash;';
  const s = (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%';
  let cls = 'neu';
  if (Math.abs(v) >= 0.03) cls = v > 0 ? 'pos' : 'neg';
  return `<span class="${cls}">${s}</span>`;
}

function fmtDir(dir) {
  if (!dir || dir === 'NONE') return '<span class="badge badge-none">&mdash;</span>';
  return dir === 'YES'
    ? '<span class="badge badge-yes">&#x25B2; YES</span>'
    : '<span class="badge badge-no">&#x25BC; NO</span>';
}

function fmtTs(ts) {
  const d = new Date(ts * 1000);
  return d.getHours() + ':' +
    String(d.getMinutes()).padStart(2, '0') + ':' +
    String(d.getSeconds()).padStart(2, '0');
}

function fmtTimeAgo(ts) {
  const secs = Math.floor(Date.now() / 1000 - ts);
  if (secs < 60) return 'just now';
  if (secs < 3600) return Math.floor(secs / 60) + 'm ago';
  return Math.floor(secs / 3600) + 'h ago';
}

function truncate(s, n = 55) {
  if (!s) return '&mdash;';
  return s.length > n ? s.slice(0, n) + '...' : s;
}

function relevanceClass(v) {
  if (v >= 0.5) return 'high';
  if (v >= 0.25) return 'medium';
  return 'low';
}

function relevanceLabel(v) {
  if (v >= 0.5) return 'HIGH';
  if (v >= 0.25) return 'MED';
  return 'LOW';
}

// ── Portfolio ─────────────────────────────────────────────────────────────

let prevPortfolioValue = null;

function renderPortfolio(p) {
  if (!p) return;
  state.portfolio = p;

  const pnlPct = p.total_pnl_pct;
  const pnlClass = pnlPct >= 0 ? 'pos' : 'neg';
  const sign = pnlPct >= 0 ? '+' : '';

  // Topbar stats
  set('total-pnl',
    `<span class="${pnlClass}">${sign}${pnlPct.toFixed(2)}% (${sign}${fmtUsd(p.total_pnl)})</span>`
  );
  set('total-value', fmtUsd(p.total_value));
  set('total-trades', p.total_trades);
  set('win-rate', p.win_rate.toFixed(1) + '%');

  // Portfolio cards
  const valEl = document.getElementById('p-value');
  if (valEl) {
    valEl.innerHTML = fmtUsd(p.total_value);
    valEl.style.color = pnlPct >= 0 ? 'var(--green)' : 'var(--red)';

    // Flash animation on value change
    if (prevPortfolioValue !== null && p.total_value !== prevPortfolioValue) {
      valEl.classList.remove('flash-up', 'flash-down');
      void valEl.offsetWidth; // force reflow
      valEl.classList.add(p.total_value > prevPortfolioValue ? 'flash-up' : 'flash-down');
    }
    prevPortfolioValue = p.total_value;
  }

  set('p-pnl',
    `<span class="${pnlClass}">${sign}${fmtUsd(p.total_pnl)} &nbsp;(${sign}${pnlPct.toFixed(2)}%)</span>`
  );
  if (p.sharpe_ratio != null) {
    const sr = p.sharpe_ratio;
    const srClass = sr >= 1.0 ? 'pos' : sr >= 0 ? 'neu' : 'neg';
    set('sharpe-ratio', `<span class="${srClass}">${sr.toFixed(2)}</span>`);
  }
  if (p.max_drawdown_pct != null) {
    set('max-drawdown', `<span class="neg">${p.max_drawdown_pct.toFixed(2)}%</span>`);
  }
  if (p.profit_factor != null) {
    const pf = p.profit_factor;
    const pfClass = pf >= 1.5 ? 'pos' : pf >= 1.0 ? 'neu' : 'neg';
    set('profit-factor', `<span class="${pfClass}">${pf >= 100 ? '\u221E' : pf.toFixed(2)}</span>`);
  }

  set('p-cash', fmtUsd(p.cash));
  set('p-exposure', `${fmtUsd(p.exposure_usd)} (${p.exposure_pct.toFixed(1)}%)`);
  // p-fees removed from simplified layout

  // Positions
  const tbody = document.getElementById('positions-body');
  const countEl = document.getElementById('position-count');
  if (!p.positions || !p.positions.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-row">No open positions</td></tr>';
    if (countEl) countEl.textContent = '0';
  } else {
    if (countEl) countEl.textContent = p.positions.length;
    tbody.innerHTML = p.positions.map(pos => {
      const pc    = pos.pnl >= 0 ? 'pos' : 'neg';
      const dClass = pos.direction === 'YES' ? 'pos' : 'neg';
      return `<tr>
        <td title="${pos.market_id}">${truncate(pos.market_id, 22)}</td>
        <td><span class="${dClass}">${pos.direction}</span></td>
        <td>${fmtUsd(pos.size_usd)}</td>
        <td>${(pos.entry_price * 100).toFixed(1)}%</td>
        <td class="${pc}">${fmtUsd(pos.pnl)} (${pos.pnl_pct.toFixed(1)}%)</td>
      </tr>`;
    }).join('');
  }
}

// ── Markets table ─────────────────────────────────────────────────────────

let selectedMarketId = null;

function showMarketsTable() {
  if (state.hasData) return;
  state.hasData = true;
  const skeleton = document.getElementById('markets-skeleton');
  const table = document.getElementById('markets-table-wrap');
  if (skeleton) skeleton.classList.add('hidden');
  if (table) table.classList.remove('hidden');
}

function renderMarkets() {
  const analyses = Object.values(state.analyses);
  if (!analyses.length) return;

  showMarketsTable();

  document.getElementById('market-count').textContent = `${analyses.length} markets`;

  // Count total active signals
  const totalSignals = analyses.reduce((sum, a) => sum + (a.signal_count || 0), 0);
  set('active-signals', `${totalSignals}`);

  // Sort: actionable trades first, then by abs effective edge
  analyses.sort((a, b) => {
    if (a.trade_direction !== 'NONE' && b.trade_direction === 'NONE') return -1;
    if (b.trade_direction !== 'NONE' && a.trade_direction === 'NONE') return 1;
    return Math.abs(b.effective_edge) - Math.abs(a.effective_edge);
  });

  const tbody = document.getElementById('markets-body');
  tbody.innerHTML = analyses.map(a => {
    const rowClass = [
      a.market_id === selectedMarketId ? 'selected' : '',
      a.trade_direction !== 'NONE'      ? 'actionable' : '',
    ].filter(Boolean).join(' ');

    const ci = `[${(a.ci_lower * 100).toFixed(0)}%, ${(a.ci_upper * 100).toFixed(0)}%]`;

    // Build mini signal dots showing which of the 8 are active
    const signalDots = ALL_SIGNALS.map(def => {
      const sig = (a.signals || []).find(s => s.source === def.key);
      const active = !!sig;
      const lr = sig ? (sig.eff_lr || sig.lr || 1) : 1;
      const dotColor = !active ? 'var(--border)' : lr > 1 ? 'var(--green)' : lr < 1 ? 'var(--red)' : 'var(--t3)';
      return `<span class="signal-dot" title="${def.label}: ${active ? 'LR=' + lr.toFixed(3) : 'inactive'}" style="background:${dotColor}"></span>`;
    }).join('');

    return `<tr class="${rowClass}" onclick="selectMarket('${a.market_id}')" title="${a.question}">
      <td>${truncate(a.question, 50)}</td>
      <td>${fmtProb(a.prior)}</td>
      <td>${fmtProb(a.posterior)}</td>
      <td>${fmtEdge(a.effective_edge)}</td>
      <td><div class="signal-dots-row">${signalDots}<span class="signal-dot-count">${a.signal_count}</span></div></td>
      <td>${fmtDir(a.trade_direction)}</td>
    </tr>`;
  }).join('');

  // Update radar with aggregate of all signals or selected market
  updateRadarFromState();
}

function updateRadarFromState() {
  const targetId = selectedMarketId || Object.keys(state.analyses)[0];
  const a = state.analyses[targetId];
  if (a && a.signals) {
    updateRadarChart(a.signals);
    const el = document.getElementById('radar-market-label');
    if (el) el.textContent = truncate(a.question, 25).replace(/&mdash;/g, '');
  }
}

function selectMarket(marketId) {
  selectedMarketId = marketId;
  renderMarkets();

  const a = state.analyses[marketId];
  if (!a) return;

  const bd = document.getElementById('signal-breakdown');
  bd.classList.remove('hidden');

  // Title
  document.getElementById('breakdown-title').textContent = truncate(a.question, 65).replace(/&mdash;/g, '');

  // Bayesian viz
  renderBayesianViz(a);

  // 8-signal grid
  renderSignalGrid(a);

  // Signal detail rows
  const container = document.getElementById('breakdown-body');
  if (!a.signals || !a.signals.length) {
    container.innerHTML = '<div class="log-empty" style="margin:12px 0">No signal data</div>';
    return;
  }

  container.innerHTML = a.signals.map(sig => {
    const lr = sig.eff_lr;
    const isYes = lr >= 1;
    const barWidth = isYes
      ? Math.min(100, (lr - 1) * 50)
      : Math.min(100, (1 - lr) * 50);
    const barColor = isYes ? 'var(--green)' : 'var(--red)';
    const lrVal = lr >= 1
      ? '+' + (lr - 1).toFixed(3)
      : (lr - 1).toFixed(3);
    const lrClass = isYes ? 'pos' : 'neg';

    return `<div class="signal-row">
      <span class="s-source" title="${sig.source}">${sourceLabel(sig.source)}</span>
      <span class="${lrClass}" style="font-size:10px;font-weight:600">${lrVal}</span>
      <span class="neu" style="font-size:10px">${sig.confidence.toFixed(2)}</span>
      <div class="lr-bar-wrap">
        <div class="lr-bar" style="width:${barWidth}%;background:${barColor}"></div>
      </div>
      <span class="s-notes" title="${sig.notes || ''}">${sig.notes || '&mdash;'}</span>
    </div>`;
  }).join('');

  // Update radar for this market
  updateRadarChart(a.signals);
  const el = document.getElementById('radar-market-label');
  if (el) el.textContent = truncate(a.question, 25).replace(/&mdash;/g, '');
}

function renderSignalGrid(a) {
  const grid = document.getElementById('signal-grid');
  if (!grid) return;

  grid.innerHTML = ALL_SIGNALS.map(def => {
    const sig = (a.signals || []).find(s => s.source === def.key);
    const active = !!sig;
    const lr = sig ? (sig.eff_lr || sig.lr || 1) : 1;
    const conf = sig ? sig.confidence : 0;
    const logLr = Math.log(lr);
    const direction = lr > 1.001 ? 'YES' : lr < 0.999 ? 'NO' : 'neutral';
    const dirClass = direction === 'YES' ? 'pos' : direction === 'NO' ? 'neg' : 'neu';
    const borderColor = active ? def.color : 'var(--border)';
    const bgGlow = active ? def.color + '12' : 'transparent';
    const lrDisplay = active ? (lr >= 1 ? '+' : '') + (lr - 1).toFixed(3) : '--';
    const confBar = Math.round(conf * 100);
    const strengthPct = Math.min(100, Math.abs(logLr) * 80);
    const strengthColor = direction === 'YES' ? 'var(--green)' : direction === 'NO' ? 'var(--red)' : 'var(--text-dim)';

    return `<div class="sg-card ${active ? 'sg-active' : 'sg-inactive'}" style="border-color:${borderColor};background:${bgGlow}" title="${def.desc}">
      <div class="sg-header">
        <span class="sg-icon" style="background:${def.color}">${def.icon}</span>
        <span class="sg-label">${def.label}</span>
        <span class="sg-status ${active ? 'sg-status-on' : ''}"></span>
      </div>
      <div class="sg-lr ${dirClass}">${lrDisplay}</div>
      <div class="sg-meta">
        <div class="sg-bar-label">Strength</div>
        <div class="sg-bar-track"><div class="sg-bar-fill" style="width:${strengthPct}%;background:${strengthColor}"></div></div>
      </div>
      <div class="sg-meta">
        <div class="sg-bar-label">Confidence</div>
        <div class="sg-bar-track"><div class="sg-bar-fill" style="width:${confBar}%;background:${def.color}"></div></div>
      </div>
      <div class="sg-direction">${direction === 'neutral' ? '&mdash;' : direction === 'YES' ? '&#x25B2; YES' : '&#x25BC; NO'}</div>
    </div>`;
  }).join('');
}

function renderBayesianViz(a) {
  const viz = document.getElementById('bayesian-viz');
  if (!viz) return;

  const priorPct = (a.prior * 100).toFixed(1);
  const postPct  = (a.posterior * 100).toFixed(1);
  const postColor = a.posterior > a.prior ? 'var(--green)' : 'var(--red)';
  const edgePct  = (Math.abs(a.effective_edge) * 100).toFixed(1);
  const edgeSign = a.effective_edge >= 0 ? '+' : '-';
  const edgeColor = a.effective_edge >= 0 ? 'var(--green)' : 'var(--red)';

  const priorFill   = (a.prior * 100).toFixed(1);
  const postFill    = (a.posterior * 100).toFixed(1);

  const ciLower = (a.ci_lower * 100).toFixed(0);
  const ciUpper = (a.ci_upper * 100).toFixed(0);

  viz.innerHTML = `
    <div class="prob-block">
      <div class="prob-label">Prior</div>
      <div class="prob-value" style="color:var(--text-mid)">${priorPct}%</div>
      <div class="prob-source">market</div>
    </div>

    <div class="arrow-section">
      <div class="arrow-bars-wrap">
        <div class="arrow-bar-row">
          <div class="arrow-bar-label">Prior</div>
          <div class="arrow-bar">
            <div class="arrow-fill" style="width:${priorFill}%;background:var(--text-dim)"></div>
          </div>
        </div>
        <div class="arrow-bar-row">
          <div class="arrow-bar-label">Posterior</div>
          <div class="arrow-bar">
            <div class="arrow-fill" style="width:${postFill}%;background:${postColor}"></div>
          </div>
        </div>
        <div class="arrow-bar-row">
          <div class="arrow-bar-label">90% CI</div>
          <div class="arrow-bar" style="position:relative">
            <div class="ci-range" style="left:${ciLower}%;width:${ciUpper - ciLower}%;background:rgba(44,181,255,0.2);border:1px solid rgba(44,181,255,0.4)"></div>
          </div>
        </div>
      </div>
      <div class="arrow-edge" style="color:${edgeColor}">
        Edge: ${edgeSign}${edgePct}% &rarr; ${fmtDir(a.trade_direction).replace(/<[^>]+>/g, '')}
      </div>
    </div>

    <div class="prob-block">
      <div class="prob-label">Posterior</div>
      <div class="prob-value" style="color:${postColor}">${postPct}%</div>
      <div class="prob-source">our model</div>
    </div>
  `;
}

function closeBreakdown() {
  document.getElementById('signal-breakdown').classList.add('hidden');
  selectedMarketId = null;
  renderMarkets();
}

// ── Activity log ──────────────────────────────────────────────────────────

const LOG_ICONS = {
  trade:            '\u26A1',
  wikipedia_spike:  '\uD83D\uDCE1',
  error:            '\u2717',
  info:             '\u25CF',
  cycle:            '\u21BB',
};

function pushLogEntry(kind, message, ts) {
  const entry = { kind, message, ts: ts || Date.now() / 1000 };
  state.events.unshift(entry);
  if (state.events.length > 200) state.events.pop();
  showTradeNotification(kind, message);
  renderLog();
}

function renderLog() {
  const wrap = document.getElementById('log-wrap');
  if (!state.events.length) {
    wrap.innerHTML = `<div class="log-empty">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" style="opacity:0.3;display:block;margin:0 auto 8px">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5"/>
        <path d="M12 8v4M12 16h.01" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
      Waiting for events...
    </div>`;
    return;
  }
  wrap.innerHTML = state.events.slice(0, 100).map(e => {
    const icon = LOG_ICONS[e.kind] || '\u00B7';
    return `<div class="log-entry ${e.kind}">
      <span class="log-ts">${fmtTs(e.ts)}</span><span class="log-icon">${icon}</span> ${e.message}
    </div>`;
  }).join('');
}

function clearLog() {
  state.events = [];
  renderLog();
}

function showTradeNotification(kind, message) {
  const container = document.getElementById('trade-notifications');
  if (!container) return;

  let typeLabel = 'TRADE';
  let cls = '';
  if (kind === 'trade' && message.toLowerCase().includes('close')) {
    typeLabel = 'CLOSED';
  } else if (kind === 'trade' && message.toLowerCase().includes('no')) {
    typeLabel = 'SELL';
    cls = 'sell';
  } else if (kind === 'trade') {
    typeLabel = 'BUY';
  } else if (kind === 'wikipedia_spike') {
    typeLabel = 'SIGNAL';
    cls = 'info-notif';
  } else {
    return; // only notify on trades and spikes
  }

  const now = new Date();
  const timeStr = now.getHours() + ':' + String(now.getMinutes()).padStart(2, '0') + ':' + String(now.getSeconds()).padStart(2, '0');

  const el = document.createElement('div');
  el.className = 'trade-notif' + (cls ? ' ' + cls : '');
  el.innerHTML = `
    <div class="trade-notif-header">
      <span class="trade-notif-type">${typeLabel}</span>
      <span class="trade-notif-time">${timeStr}</span>
    </div>
    <div class="trade-notif-body">${message}</div>
  `;
  container.appendChild(el);

  // Remove after animation completes (5s)
  setTimeout(() => { if (el.parentNode) el.remove(); }, 5000);

  // Cap at 4 visible notifications
  while (container.children.length > 4) {
    container.removeChild(container.firstChild);
  }
}

// ── News Feed ──────────────────────────────────────────────────────────────

function pushNewsItem(item) {
  state.news.unshift(item);
  if (state.news.length > 100) state.news.pop();
  renderNewsFeed();
  updateNewsTicker();
}

function renderNewsFeed() {
  const feed = document.getElementById('news-feed');
  const countEl = document.getElementById('news-count');
  if (countEl) countEl.textContent = `${state.news.length} articles`;

  if (!state.news.length) {
    feed.innerHTML = `<div class="news-empty">
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" style="opacity:0.3;display:block;margin:0 auto 6px">
        <rect x="2" y="3" width="16" height="14" rx="2" stroke="currentColor" stroke-width="1.2"/>
        <path d="M5 7h10M5 10h7M5 13h4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
      </svg>
      Monitoring 15 RSS feeds...
    </div>`;
    return;
  }

  feed.innerHTML = state.news.slice(0, 50).map(n => {
    const relCls = relevanceClass(n.relevance);
    const relLabel = relevanceLabel(n.relevance);
    const sourceName = (n.source || 'RSS').replace(/_/g, ' ');
    return `<div class="news-item">
      <div class="news-item-header">
        <span class="news-source">${sourceName}</span>
        <span class="news-relevance-badge ${relCls}">${relLabel}</span>
        <span class="news-time">${fmtTimeAgo(n.ts)}</span>
      </div>
      <div class="news-title">${n.title}</div>
    </div>`;
  }).join('');
}

function updateNewsTicker() {
  const content = document.getElementById('ticker-content');
  if (!state.news.length) return;

  // Build ticker from recent news items (duplicate for seamless scroll)
  const items = state.news.slice(0, 20);
  const buildItems = items.map(n => {
    const relCls = relevanceClass(n.relevance);
    const sourceName = (n.source || 'RSS').replace(/_/g, ' ');
    return `<span class="ticker-item">
      <span class="ticker-source">${sourceName}</span>
      <span class="ticker-title">${truncate(n.title, 80)}</span>
      <span class="ticker-relevance ${relCls}">${(n.relevance * 100).toFixed(0)}%</span>
    </span>
    <span class="ticker-separator">\u2022</span>`;
  }).join('');

  // Duplicate for seamless looping
  content.innerHTML = buildItems + buildItems;
}

// ── Uptime ────────────────────────────────────────────────────────────────

function updateUptime() {
  if (!state.startedAt) return;
  const s = Math.floor(Date.now() / 1000 - state.startedAt);
  const h = Math.floor(s / 3600).toString().padStart(2, '0');
  const m = Math.floor((s % 3600) / 60).toString().padStart(2, '0');
  const sec = (s % 60).toString().padStart(2, '0');
  document.getElementById('uptime').textContent = `${h}:${m}:${sec}`;
}

// ── WebSocket ─────────────────────────────────────────────────────────────

function setWsStatus(ok) {
  const dot   = document.getElementById('ws-dot');
  const label = document.getElementById('ws-status');
  if (ok) {
    dot.className  = 'ws-dot connected';
    label.textContent = 'live';
    state.connected = true;
  } else {
    dot.className  = 'ws-dot error';
    label.textContent = 'reconnecting...';
    state.connected = false;
  }
}

function handleMessage(msg) {
  switch (msg.type) {
    case 'snapshot':
      handleSnapshot(msg.data);
      break;
    case 'portfolio':
      renderPortfolio(msg.data);
      if (state.pnlHistory.length) updateChart(state.pnlHistory);
      break;
    case 'analysis':
      state.analyses[msg.data.market_id] = msg.data;
      renderMarkets();
      if (selectedMarketId === msg.data.market_id) {
        renderBayesianViz(msg.data);
        renderSignalGrid(msg.data);
        updateRadarChart(msg.data.signals || []);
      }
      break;
    case 'event':
      pushLogEntry(msg.data.kind, msg.data.message, msg.data.ts);
      break;
    case 'news':
      pushNewsItem(msg.data);
      break;
    case 'ping':
      break;
  }
}

function handleSnapshot(data) {
  state.startedAt  = data.started_at;
  state.pnlHistory = data.pnl_history || [];

  const mode = (data.trading_mode || 'paper').toUpperCase();
  const badge = document.getElementById('mode-badge');
  badge.textContent = mode;
  if (data.trading_mode === 'live') badge.classList.add('live');

  if (data.portfolio) renderPortfolio(data.portfolio);
  updateChart(state.pnlHistory);

  (data.analyses || []).forEach(a => { state.analyses[a.market_id] = a; });
  renderMarkets();

  (data.events || []).forEach(e => state.events.push(e));
  state.events.reverse();
  renderLog();

  // Load initial news items
  if (data.news && data.news.length) {
    data.news.reverse().forEach(n => {
      state.news.unshift(n);
    });
    renderNewsFeed();
    updateNewsTicker();
  }
}

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    setWsStatus(true);
    pushLogEntry('info', 'Connected to agent');
  };

  ws.onmessage = e => {
    try { handleMessage(JSON.parse(e.data)); } catch (_) {}
  };

  ws.onerror = () => setWsStatus(false);

  ws.onclose = () => {
    setWsStatus(false);
    setTimeout(connect, 3000);
  };
}

// ── Utility ───────────────────────────────────────────────────────────────

function set(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

// ── Init ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initChart();
  initRadarChart();
  initCalibrationChart();
  connect();
  setInterval(updateUptime, 1000);
  // Refresh news time-ago labels every 30s
  setInterval(() => { if (state.news.length) renderNewsFeed(); }, 30000);
});
