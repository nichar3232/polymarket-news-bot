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
        borderColor: '#00e676',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
        fill: {
          target: 'origin',
          above: 'rgba(0,230,118,0.06)',
          below: 'rgba(255,71,87,0.06)',
        },
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: {
        x: {
          display: false,
          ticks: { maxTicksLimit: 6 },
        },
        y: {
          grid: { color: '#1e2435' },
          ticks: {
            color: '#5a6380',
            font: { family: 'monospace', size: 10 },
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
  const isNeg = vals.length && vals[vals.length - 1] < 0;
  pnlChart.data.datasets[0].borderColor = isNeg ? '#ff4757' : '#00e676';
  pnlChart.update('none');
}

// ── Formatting helpers ─────────────────────────────────────────────────────

function fmtPct(v, decimals = 1) {
  if (v == null) return '—';
  const s = (v >= 0 ? '+' : '') + v.toFixed(decimals) + '%';
  return `<span class="${v >= 0 ? 'pos' : 'neg'}">${s}</span>`;
}

function fmtUsd(v) {
  if (v == null) return '—';
  return '$' + v.toFixed(2);
}

function fmtProb(v) {
  if (v == null) return '—';
  const pct = (v * 100).toFixed(1);
  const fill = Math.round(v * 100);
  return `<span class="prob-meter">
    <span>${pct}%</span>
    <span class="meter-track"><span class="meter-fill" style="width:${fill}%"></span></span>
  </span>`;
}

function fmtEdge(v) {
  if (v == null) return '—';
  const s = (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%';
  return `<span class="${Math.abs(v) >= 0.03 ? (v > 0 ? 'pos' : 'neg') : 'neu'}">${s}</span>`;
}

function fmtDir(dir) {
  if (!dir || dir === 'NONE') return '<span class="badge badge-none">—</span>';
  return dir === 'YES'
    ? '<span class="badge badge-yes">YES</span>'
    : '<span class="badge badge-no">NO</span>';
}

function fmtTs(ts) {
  const d = new Date(ts * 1000);
  return d.getHours() + ':' + String(d.getMinutes()).padStart(2, '0') + ':' + String(d.getSeconds()).padStart(2, '0');
}

function truncate(s, n = 55) {
  return s.length > n ? s.slice(0, n) + '…' : s;
}

// ── Portfolio ─────────────────────────────────────────────────────────────

function renderPortfolio(p) {
  if (!p) return;
  state.portfolio = p;

  const pnlPct = p.total_pnl_pct;
  const pnlClass = pnlPct >= 0 ? 'pos' : 'neg';
  const sign = pnlPct >= 0 ? '+' : '';

  // Topbar
  set('total-pnl', `<span class="${pnlClass}">${sign}${pnlPct.toFixed(2)}% (${sign}${fmtUsd(p.total_pnl)})</span>`);
  set('total-value', fmtUsd(p.total_value));
  set('total-trades', p.total_trades);
  set('win-rate', p.win_rate.toFixed(1) + '%');

  // Panel
  set('p-start', fmtUsd(p.starting_value));
  set('p-value', fmtUsd(p.total_value));
  set('p-pnl', `<span class="${pnlClass}">${sign}${fmtUsd(p.total_pnl)} (${sign}${pnlPct.toFixed(2)}%)</span>`);
  set('p-cash', fmtUsd(p.cash));
  set('p-exposure', `${fmtUsd(p.exposure_usd)} (${p.exposure_pct.toFixed(1)}%)`);
  set('p-fees', fmtUsd(p.fees_paid));

  // Positions table
  const tbody = document.getElementById('positions-body');
  if (!p.positions || !p.positions.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-row">No open positions</td></tr>';
  } else {
    tbody.innerHTML = p.positions.map(pos => {
      const pc = pos.pnl >= 0 ? 'pos' : 'neg';
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

  // Sort: actionable trades first, then by effective edge magnitude
  analyses.sort((a, b) => {
    if (a.trade_direction !== 'NONE' && b.trade_direction === 'NONE') return -1;
    if (b.trade_direction !== 'NONE' && a.trade_direction === 'NONE') return 1;
    return Math.abs(b.effective_edge) - Math.abs(a.effective_edge);
  });

  const tbody = document.getElementById('markets-body');
  tbody.innerHTML = analyses.map(a => {
    const rowClass = a.market_id === selectedMarketId ? ' class="selected"' : '';
    const ciStr = `[${(a.ci_lower * 100).toFixed(0)}, ${(a.ci_upper * 100).toFixed(0)}]`;
    return `<tr${rowClass} onclick="selectMarket('${a.market_id}')" title="${a.question}">
      <td>${truncate(a.question, 52)}</td>
      <td>${fmtProb(a.prior)}</td>
      <td>${fmtProb(a.posterior)}</td>
      <td>${fmtEdge(a.effective_edge)}</td>
      <td><span class="neu">${a.signal_count}</span></td>
      <td><span class="neu" style="font-size:10px">${ciStr}</span></td>
      <td>${fmtDir(a.trade_direction)}</td>
    </tr>`;
  }).join('');
}

function selectMarket(marketId) {
  selectedMarketId = marketId;
  renderMarkets();  // re-render to highlight selected row

  const a = state.analyses[marketId];
  if (!a) return;

  const bd = document.getElementById('signal-breakdown');
  bd.classList.remove('hidden');

  document.getElementById('breakdown-title').textContent = truncate(a.question, 60);

  // Signal rows
  const container = document.getElementById('breakdown-body');
  container.innerHTML = a.signals.map(sig => {
    const lr = sig.eff_lr;
    const isYes = lr >= 1;
    const barWidth = isYes
      ? Math.min(100, (lr - 1) * 40)
      : Math.min(100, (1 - lr) * 40);
    const barColor = isYes ? 'var(--green)' : 'var(--red)';
    const lrStr = lr >= 1 ? '+' + (lr - 1).toFixed(3) : (lr - 1).toFixed(3);
    return `<div class="signal-row">
      <span class="s-source">${sig.source}</span>
      <span class="${isYes ? 'pos' : 'neg'}" style="font-size:10px">${lrStr}</span>
      <span class="neu" style="font-size:10px">conf ${sig.confidence.toFixed(2)}</span>
      <div class="lr-bar-wrap"><div class="lr-bar" style="width:${barWidth}%;background:${barColor}"></div></div>
      <span class="neu" style="font-size:10px;white-space:normal">${sig.notes || '—'}</span>
    </div>`;
  }).join('');

  // Bayesian viz
  renderBayesianViz(a);
}

function renderBayesianViz(a) {
  const viz = document.getElementById('bayesian-viz');
  const priorPct = (a.prior * 100).toFixed(1);
  const postPct  = (a.posterior * 100).toFixed(1);
  const postColor = a.posterior > a.prior ? 'var(--green)' : 'var(--red)';
  const edgePct = ((a.effective_edge) * 100).toFixed(1);
  const edgeSign = a.effective_edge >= 0 ? '+' : '';
  const edgeColor = a.effective_edge >= 0 ? 'var(--green)' : 'var(--red)';

  // Prior bar: fill = prior%
  // Posterior bar: fill = posterior%
  viz.innerHTML = `
    <div class="prob-block">
      <div class="prob-label">PRIOR</div>
      <div class="prob-value" style="color:var(--text-dim)">${priorPct}%</div>
      <div style="font-size:9px;color:var(--text-dim)">market</div>
    </div>
    <div class="arrow-section">
      <div style="font-size:9px;color:var(--text-dim)">Prior</div>
      <div class="arrow-bar">
        <div class="arrow-fill" style="width:${a.prior * 100}%;background:var(--text-dim);left:0"></div>
      </div>
      <div class="arrow-bar" style="margin-top:4px">
        <div class="arrow-fill" style="width:${a.posterior * 100}%;background:${postColor};left:0"></div>
      </div>
      <div style="font-size:9px;color:var(--text-dim)">Posterior</div>
      <div style="margin-top:6px;font-size:11px;font-weight:700;color:${edgeColor}">
        Edge: ${edgeSign}${edgePct}%
        &nbsp;→&nbsp; ${fmtDir(a.trade_direction).replace(/<[^>]+>/g, '')}
      </div>
    </div>
    <div class="prob-block">
      <div class="prob-label">POSTERIOR</div>
      <div class="prob-value" style="color:${postColor}">${postPct}%</div>
      <div style="font-size:9px;color:var(--text-dim)">our estimate</div>
    </div>
  `;
}

function closeBreakdown() {
  document.getElementById('signal-breakdown').classList.add('hidden');
  selectedMarketId = null;
  renderMarkets();
}

// ── Activity log ──────────────────────────────────────────────────────────

function pushLogEntry(kind, message, ts) {
  const entry = { kind, message, ts: ts || Date.now() / 1000 };
  state.events.unshift(entry);
  if (state.events.length > 200) state.events.pop();
  renderLog();
}

function renderLog() {
  const wrap = document.getElementById('log-wrap');
  if (!state.events.length) {
    wrap.innerHTML = '<div class="log-empty">Waiting for events…</div>';
    return;
  }
  wrap.innerHTML = state.events.slice(0, 80).map(e => {
    const ts = fmtTs(e.ts);
    return `<div class="log-entry ${e.kind}">
      <span class="log-ts">${ts}</span>${e.message}
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
  const dot = document.getElementById('ws-dot');
  const txt = document.getElementById('ws-status');
  if (ok) {
    dot.className = 'ws-indicator connected';
    txt.textContent = 'live';
    state.connected = true;
  } else {
    dot.className = 'ws-indicator error';
    txt.textContent = 'reconnecting…';
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
  state.startedAt = data.started_at;
  state.pnlHistory = data.pnl_history || [];

  document.getElementById('mode-badge').textContent = (data.trading_mode || 'paper').toUpperCase();
  if (data.trading_mode === 'live') {
    document.getElementById('mode-badge').classList.add('live');
  }

  if (data.portfolio) renderPortfolio(data.portfolio);
  updateChart(state.pnlHistory);

  (data.analyses || []).forEach(a => { state.analyses[a.market_id] = a; });
  renderMarkets();

  (data.events || []).forEach(e => {
    state.events.push(e);
  });
  state.events.reverse();  // newest first
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
    // Reconnect after 3s
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
