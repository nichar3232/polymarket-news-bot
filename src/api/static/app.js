/**
 * Polymarket News Bot — Dashboard
 *
 * Connects via WebSocket for real-time updates.
 * Falls back to polling /api/state every 10s on WS failure.
 */

'use strict';

// ── State ──────────────────────────────────────────────────────────────────

const state = {
  portfolio:  null,
  analyses:   {},   // market_id → analysis object
  events:     [],
  pnlHistory: [],
  startedAt:  null,
  connected:  false,
};

// ── Chart ──────────────────────────────────────────────────────────────────

let pnlChart = null;

function initChart() {
  const ctx = document.getElementById('pnl-chart').getContext('2d');
  pnlChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: 'P&L %',
        data: [],
        borderColor: '#0de88a',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.4,
        fill: {
          target: 'origin',
          above: 'rgba(13,232,138,0.07)',
          below: 'rgba(255,77,106,0.07)',
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
          backgroundColor: '#111620',
          borderColor: '#273050',
          borderWidth: 1,
          titleColor: '#4e5a7a',
          bodyColor: '#e4eaf8',
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
          grid: { color: '#1c2236' },
          ticks: {
            color: '#4e5a7a',
            font: { family: 'JetBrains Mono, monospace', size: 10 },
            callback: v => v.toFixed(1) + '%',
          },
          border: { display: false },
        },
      },
    },
  });
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
  pnlChart.data.datasets[0].borderColor = last < 0 ? '#ff4d6a' : '#0de88a';
  pnlChart.update('none');
}

// ── Formatting helpers ─────────────────────────────────────────────────────

function fmtPct(v, decimals = 2) {
  if (v == null) return '—';
  const s = (v >= 0 ? '+' : '') + v.toFixed(decimals) + '%';
  return `<span class="${v >= 0 ? 'pos' : 'neg'}">${s}</span>`;
}

function fmtUsd(v) {
  if (v == null) return '—';
  return '$' + v.toFixed(2);
}

function probColor(v) {
  // Returns a CSS class for the probability meter fill
  if (v >= 0.6) return 'meter-fill-hi';
  if (v >= 0.35) return 'meter-fill-mid';
  return 'meter-fill-lo';
}

function fmtProb(v) {
  if (v == null) return '—';
  const pct = (v * 100).toFixed(1);
  const fill = Math.round(v * 100);
  const cls = probColor(v);
  return `<span class="prob-meter">
    <span>${pct}%</span>
    <span class="meter-track"><span class="meter-fill ${cls}" style="width:${fill}%"></span></span>
  </span>`;
}

function fmtEdge(v) {
  if (v == null) return '—';
  const s = (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%';
  let cls = 'neu';
  if (Math.abs(v) >= 0.03) cls = v > 0 ? 'pos' : 'neg';
  return `<span class="${cls}">${s}</span>`;
}

function fmtDir(dir) {
  if (!dir || dir === 'NONE') return '<span class="badge badge-none">—</span>';
  return dir === 'YES'
    ? '<span class="badge badge-yes">▲ YES</span>'
    : '<span class="badge badge-no">▼ NO</span>';
}

function fmtTs(ts) {
  const d = new Date(ts * 1000);
  return d.getHours() + ':' +
    String(d.getMinutes()).padStart(2, '0') + ':' +
    String(d.getSeconds()).padStart(2, '0');
}

function truncate(s, n = 55) {
  if (!s) return '—';
  return s.length > n ? s.slice(0, n) + '…' : s;
}

// Human-readable signal source names
const SOURCE_LABELS = {
  microstructure_vpin:      'Microstructure (VPIN)',
  microstructure_ofi:       'Order Flow Imbalance',
  microstructure_spread:    'Bid-Ask Spread',
  cross_market:             'Cross-Market Arb',
  news_relevance:           'News Relevance',
  resolution_signal:        'Resolution Monitor',
  llm_decomposition:        'LLM Superforecaster',
  wikipedia_edit_velocity:  'Wikipedia Velocity',
};

function sourceLabel(raw) {
  return SOURCE_LABELS[raw] || raw.replace(/_/g, ' ');
}

// ── Portfolio ─────────────────────────────────────────────────────────────

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
  set('p-value', fmtUsd(p.total_value));
  set('p-pnl',
    `<span class="${pnlClass}">${sign}${fmtUsd(p.total_pnl)} &nbsp;(${sign}${pnlPct.toFixed(2)}%)</span>`
  );
  set('p-cash', fmtUsd(p.cash));
  set('p-exposure', `${fmtUsd(p.exposure_usd)} (${p.exposure_pct.toFixed(1)}%)`);
  set('p-fees', fmtUsd(p.fees_paid));

  // Color the main card value
  const valEl = document.getElementById('p-value');
  if (valEl) valEl.style.color = pnlPct >= 0 ? 'var(--green)' : 'var(--red)';

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

function renderMarkets() {
  const analyses = Object.values(state.analyses);
  if (!analyses.length) return;

  document.getElementById('market-count').textContent = `${analyses.length} markets`;

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
    const signalBadge = `<span class="ph-count">${a.signal_count}</span>`;

    return `<tr class="${rowClass}" onclick="selectMarket('${a.market_id}')" title="${a.question}">
      <td>${truncate(a.question, 54)}</td>
      <td>${fmtProb(a.prior)}</td>
      <td>${fmtProb(a.posterior)}</td>
      <td>${fmtEdge(a.effective_edge)}</td>
      <td>${signalBadge}</td>
      <td><span class="neu" style="font-size:10px">${ci}</span></td>
      <td>${fmtDir(a.trade_direction)}</td>
    </tr>`;
  }).join('');
}

function selectMarket(marketId) {
  selectedMarketId = marketId;
  renderMarkets();

  const a = state.analyses[marketId];
  if (!a) return;

  const bd = document.getElementById('signal-breakdown');
  bd.classList.remove('hidden');

  // Title
  document.getElementById('breakdown-title').textContent = truncate(a.question, 65);

  // Bayesian viz first
  renderBayesianViz(a);

  // Signal rows
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
      <span class="s-notes" title="${sig.notes || ''}">${sig.notes || '—'}</span>
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
  const edgeSign = a.effective_edge >= 0 ? '+' : '−';
  const edgeColor = a.effective_edge >= 0 ? 'var(--green)' : 'var(--red)';

  const priorFill   = (a.prior * 100).toFixed(1);
  const postFill    = (a.posterior * 100).toFixed(1);

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
  trade:            '⚡',
  wikipedia_spike:  '📡',
  error:            '✗',
  info:             '●',
  cycle:            '↻',
};

function pushLogEntry(kind, message, ts) {
  const entry = { kind, message, ts: ts || Date.now() / 1000 };
  state.events.unshift(entry);
  if (state.events.length > 200) state.events.pop();
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
      Waiting for events…
    </div>`;
    return;
  }
  wrap.innerHTML = state.events.slice(0, 100).map(e => {
    const icon = LOG_ICONS[e.kind] || '·';
    return `<div class="log-entry ${e.kind}">
      <span class="log-ts">${fmtTs(e.ts)}</span>${icon} ${e.message}
    </div>`;
  }).join('');
}

function clearLog() {
  state.events = [];
  renderLog();
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
    label.textContent = 'reconnecting…';
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
      }
      break;
    case 'event':
      pushLogEntry(msg.data.kind, msg.data.message, msg.data.ts);
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
  connect();
  setInterval(updateUptime, 1000);
});
