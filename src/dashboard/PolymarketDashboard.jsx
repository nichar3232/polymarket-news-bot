import React, { useState, useEffect, useRef } from 'react';

// ─── Mock Data ──────────────────────────────────────────────────────────────

const PORTFOLIO = {
  totalValue: 1004.80,
  pnl: 4.80,
  pnlPct: 0.48,
  cash: 953.19,
  exposure: 56.00,
  exposurePct: 5.6,
  trades: 5,
  winRate: 60.0,
  sharpe: 0.65,
  maxDD: 1.42,
  profitFactor: 2.38,
};

const PNL_HISTORY = [
  0, 0.1, -0.05, 0.15, 0.3, 0.2, 0.4, 0.35, 0.5, 0.45, 0.6, 0.55,
  0.7, 0.8, 0.75, 0.9, 1.0, 0.95, 1.1, 1.2, 1.15, 1.3, 1.25, 1.4,
  1.5, 1.6, 1.55, 1.7, 1.8, 1.75, 1.9, 2.0, 1.95, 2.1, 2.2, 2.3,
];

const POSITIONS = [
  { id: '0xbb57cc...6c28c6', dir: 'NO', size: 28.00, entry: 0.513, current: 0.498, pnl: 0.83 },
  { id: '0x9c1a95...e90c42', dir: 'YES', size: 28.00, entry: 0.540, current: 0.557, pnl: 0.88 },
];

const CALIBRATION = [
  { bucket: '0-20%', predicted: 0.10, actual: 0.07 },
  { bucket: '20-40%', predicted: 0.30, actual: 0.28 },
  { bucket: '40-60%', predicted: 0.50, actual: 0.52 },
  { bucket: '60-80%', predicted: 0.70, actual: 0.73 },
  { bucket: '80-100%', predicted: 0.90, actual: 0.92 },
];

const MARKETS = [
  { q: 'Will Jesus Christ return before GTA VI?', prior: 48.5, posterior: 51.2, edge: 2.7 },
  { q: 'Will bitcoin hit $1m before GTA VI?', prior: 48.7, posterior: 44.1, edge: -4.6 },
  { q: 'Will Rihanna drop a new album in 2026?', prior: 35.2, posterior: 38.8, edge: 3.6 },
  { q: 'Colorado Avalanche win 2026 Stanley Cup?', prior: 20.2, posterior: 18.5, edge: -1.7 },
  { q: 'Will the Fed cut rates by June 2026?', prior: 38.0, posterior: 31.4, edge: -6.6 },
  { q: 'Trump impose new EU tariffs by April?', prior: 62.0, posterior: 67.3, edge: 5.3 },
  { q: 'Ukraine ceasefire agreement by end 2026?', prior: 32.0, posterior: 35.1, edge: 3.1 },
  { q: 'Bitcoin exceed $150k before October 2026?', prior: 44.0, posterior: 47.8, edge: 3.8 },
  { q: 'Congress pass AI regulation in 2026?', prior: 25.0, posterior: 21.3, edge: -3.7 },
  { q: 'S&P 500 close above 6000 end of 2026?', prior: 55.0, posterior: 59.2, edge: 4.2 },
  { q: 'Will OpenAI release GPT-5 in 2026?', prior: 67.0, posterior: 71.5, edge: 4.5 },
  { q: 'India GDP growth exceed 7% in 2026?', prior: 42.0, posterior: 39.8, edge: -2.2 },
];

const RADAR_LABELS = ['VPIN', 'Spread', 'Cross-Mkt', 'News RSS', 'GDELT', 'LLM', 'Wikipedia', 'Reddit'];
const RADAR_VALUES = [0.62, 0.35, 0.71, 0.48, 0.29, 0.55, 0.18, 0.08];

const ACTIVITY = [
  { ts: '14:42:11', kind: 'cycle', msg: 'Cycle 23: evaluating 12 markets' },
  { ts: '14:41:58', kind: 'info', msg: 'RSS: 4 new articles from Reuters, WSJ, AP' },
  { ts: '14:41:45', kind: 'wiki', msg: "Wikipedia spike: 'EU-US_trade' — 6 edits/5min (3.5x baseline)" },
  { ts: '14:41:30', kind: 'info', msg: 'Skipped 10 markets: edge < 5% threshold' },
  { ts: '14:41:02', kind: 'cycle', msg: 'Cycle 22: evaluating 12 markets' },
  { ts: '14:40:48', kind: 'trade', msg: 'BUY NO 0xbb57cc…6c28c6 | $28.00 @ 0.513 | Edge: -0.068' },
  { ts: '14:40:33', kind: 'info', msg: 'RSS: 2 new articles from BBC, CNBC' },
  { ts: '14:40:15', kind: 'cycle', msg: 'Cycle 21: evaluating 12 markets' },
  { ts: '14:39:58', kind: 'trade', msg: 'BUY YES 0x9c1a95…e90c42 | $28.00 @ 0.540 | Edge: +0.053' },
  { ts: '14:39:40', kind: 'wiki', msg: "Wikipedia spike: 'Bitcoin' — 4 edits/5min (2.8x baseline)" },
  { ts: '14:39:22', kind: 'info', msg: 'Skipped 8 markets: edge < 5% threshold' },
  { ts: '14:39:05', kind: 'cycle', msg: 'Cycle 20: evaluating 12 markets' },
  { ts: '14:38:50', kind: 'info', msg: 'Agent started with $1,000.00 | Model v2 loaded' },
];

const NEWS = [
  { source: 'WSJ', priority: 'HIGH', time: '3m ago', title: 'Fed minutes show officials concerned about persistent inflation' },
  { source: 'BBC', priority: 'MED', time: '8m ago', title: 'G7 leaders to discuss Ukraine reconstruction framework at summit' },
  { source: 'FT', priority: 'HIGH', time: '12m ago', title: 'European banks report strong Q1 trading revenue across divisions' },
  { source: 'REUTERS', priority: 'HIGH', time: '15m ago', title: 'Trump administration circulates draft tariff proposal targeting EU' },
  { source: 'COINDESK', priority: 'MED', time: '22m ago', title: 'Bitcoin ETF weekly inflows reach $1.8B institutional record' },
  { source: 'CNBC', priority: 'LOW', time: '28m ago', title: 'Nvidia revenue guidance exceeds analyst expectations' },
  { source: 'AP', priority: 'MED', time: '34m ago', title: 'Ukraine peace talks tentatively scheduled for May summit' },
];

// ─── Sparkline ──────────────────────────────────────────────────────────────

function Sparkline({ data, width = 220, height = 48 }) {
  if (!data.length) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / range) * (height - 4) - 2;
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <polyline fill="none" stroke="#F5A623" strokeWidth="1.5" points={points} />
    </svg>
  );
}

// ─── Radar Chart ────────────────────────────────────────────────────────────

function RadarChart({ labels, values, size = 240 }) {
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 30;
  const n = labels.length;
  const angle = (i) => (Math.PI * 2 * i) / n - Math.PI / 2;

  const gridLevels = [0.25, 0.5, 0.75, 1.0];
  const pointCoords = values.map((v, i) => ({
    x: cx + Math.cos(angle(i)) * r * v,
    y: cy + Math.sin(angle(i)) * r * v,
  }));
  const polygon = pointCoords.map(p => `${p.x},${p.y}`).join(' ');

  return (
    <svg width={size} height={size} style={{ display: 'block', margin: '0 auto' }}>
      {gridLevels.map((lv, li) => (
        <polygon
          key={li}
          fill="none"
          stroke="rgba(255,255,255,0.05)"
          strokeWidth="1"
          points={Array.from({ length: n }, (_, i) => {
            const x = cx + Math.cos(angle(i)) * r * lv;
            const y = cy + Math.sin(angle(i)) * r * lv;
            return `${x},${y}`;
          }).join(' ')}
        />
      ))}
      {labels.map((_, i) => (
        <line
          key={i}
          x1={cx} y1={cy}
          x2={cx + Math.cos(angle(i)) * r}
          y2={cy + Math.sin(angle(i)) * r}
          stroke="rgba(255,255,255,0.04)"
          strokeWidth="1"
        />
      ))}
      <polygon fill="rgba(245,166,35,0.08)" stroke="#F5A623" strokeWidth="1.5" points={polygon} />
      {pointCoords.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="3" fill="#F5A623" />
      ))}
      {labels.map((label, i) => {
        const lx = cx + Math.cos(angle(i)) * (r + 18);
        const ly = cy + Math.sin(angle(i)) * (r + 18);
        return (
          <text
            key={i} x={lx} y={ly}
            fill="rgba(255,255,255,0.4)"
            fontSize="8" fontFamily="'Barlow Condensed', 'Helvetica Neue', sans-serif"
            textAnchor="middle" dominantBaseline="middle"
            letterSpacing="0.08em"
          >
            {label.toUpperCase()}
          </text>
        );
      })}
    </svg>
  );
}

// ─── Calibration Chart ──────────────────────────────────────────────────────

function CalibrationChart({ data }) {
  const barH = 14;
  const gap = 6;
  const labelW = 48;
  const chartW = 160;

  return (
    <div style={{ padding: '4px 0' }}>
      {data.map((d, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: gap }}>
          <span style={{ ...S.mono, fontSize: 9, color: 'rgba(255,255,255,0.3)', width: labelW, textAlign: 'right' }}>
            {d.bucket}
          </span>
          <div style={{ width: chartW, position: 'relative', height: barH }}>
            <div style={{
              position: 'absolute', top: 0, left: 0, height: '50%',
              width: `${d.predicted * 100}%`, background: 'rgba(0,212,255,0.2)',
              borderRight: '1px solid rgba(0,212,255,0.5)',
            }} />
            <div style={{
              position: 'absolute', bottom: 0, left: 0, height: '50%',
              width: `${d.actual * 100}%`, background: 'rgba(245,166,35,0.2)',
              borderRight: '1px solid rgba(245,166,35,0.6)',
            }} />
          </div>
          <span style={{ ...S.mono, fontSize: 8, color: 'rgba(255,255,255,0.25)', width: 30 }}>
            {(d.actual * 100).toFixed(0)}%
          </span>
        </div>
      ))}
      <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 4 }}>
        <span style={{ fontSize: 8, color: 'rgba(0,212,255,0.5)', fontFamily: S.condensed.fontFamily }}>■ PREDICTED</span>
        <span style={{ fontSize: 8, color: 'rgba(245,166,35,0.5)', fontFamily: S.condensed.fontFamily }}>■ ACTUAL</span>
      </div>
    </div>
  );
}

// ─── Clock ──────────────────────────────────────────────────────────────────

function useClock() {
  const [time, setTime] = useState('00:00:00');
  useEffect(() => {
    const tick = () => {
      const d = new Date();
      setTime(
        String(d.getHours()).padStart(2, '0') + ':' +
        String(d.getMinutes()).padStart(2, '0') + ':' +
        String(d.getSeconds()).padStart(2, '0')
      );
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return time;
}

// ─── Styles ─────────────────────────────────────────────────────────────────

const S = {
  mono: { fontFamily: "'IBM Plex Mono', 'Courier New', monospace" },
  condensed: { fontFamily: "'Barlow Condensed', 'Helvetica Neue', Arial Narrow, sans-serif" },
  amber: '#F5A623',
  blue: '#00D4FF',
  rose: '#C4737A',
  bg: '#0A0A0B',
  bg2: '#0F0F11',
  border: 'rgba(255,255,255,0.08)',
  t1: 'rgba(255,255,255,0.88)',
  t2: 'rgba(255,255,255,0.50)',
  t3: 'rgba(255,255,255,0.25)',
};

// ─── Main Component ─────────────────────────────────────────────────────────

export default function PolymarketDashboard() {
  const clock = useClock();

  return (
    <div style={{
      background: S.bg,
      color: S.t2,
      fontFamily: S.condensed.fontFamily,
      fontSize: 12,
      height: '100vh',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
      position: 'relative',
    }}>
      {/* Scanline overlay */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 999, pointerEvents: 'none',
        background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,255,255,0.015) 2px, rgba(255,255,255,0.015) 4px)',
      }} />

      {/* ── TOPBAR ────────────────────────────────────────── */}
      <header style={{
        height: 44,
        background: S.bg2,
        borderBottom: `1px solid ${S.border}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 14px',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ ...S.condensed, fontSize: 14, fontWeight: 700, color: S.t1, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            Polymarket Agent
          </span>
          <span style={{
            fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
            padding: '2px 7px', background: 'rgba(245,166,35,0.1)',
            color: S.amber, border: `1px solid rgba(245,166,35,0.2)`,
          }}>PAPER</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#4ade80' }} />
            <span style={{ fontSize: 9, color: S.t3 }}>LIVE</span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
          {[
            ['TRADES', PORTFOLIO.trades],
            ['WIN RATE', PORTFOLIO.winRate.toFixed(1) + '%'],
            ['SHARPE', PORTFOLIO.sharpe.toFixed(2)],
            ['MAX DD', PORTFOLIO.maxDD.toFixed(2) + '%'],
            ['PROFIT F.', PORTFOLIO.profitFactor.toFixed(2)],
          ].map(([label, val], i) => (
            <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '0 10px' }}>
              <span style={{ ...S.condensed, fontSize: 8, color: S.t3, letterSpacing: '0.08em', textTransform: 'uppercase' }}>{label}</span>
              <span style={{ ...S.mono, fontSize: 12, fontWeight: 600, color: S.t1 }}>{val}</span>
            </div>
          ))}
        </div>

        <span style={{ ...S.mono, fontSize: 10, color: S.t3, letterSpacing: '0.04em' }}>{clock}</span>
      </header>

      {/* ── GRID ──────────────────────────────────────────── */}
      <div style={{
        flex: 1,
        display: 'grid',
        gridTemplateColumns: '270px 1fr 270px',
        gap: 1,
        background: S.border,
        overflow: 'hidden',
      }}>

        {/* ── LEFT PANEL ─────────────────────────────────── */}
        <div style={{ background: S.bg, padding: 12, overflowY: 'auto' }}>
          <SectionLabel>PORTFOLIO</SectionLabel>

          {/* Big value */}
          <div style={{ background: S.bg2, border: `1px solid ${S.border}`, padding: '12px 14px', marginBottom: 4 }}>
            <div style={{ ...S.condensed, fontSize: 8, color: S.t3, letterSpacing: '0.1em', marginBottom: 2 }}>TOTAL VALUE</div>
            <div style={{ ...S.mono, fontSize: 28, fontWeight: 700, color: S.t1, letterSpacing: '-0.02em', lineHeight: 1 }}>
              ${PORTFOLIO.totalValue.toFixed(2)}
            </div>
            <div style={{ ...S.mono, fontSize: 12, color: S.amber, marginTop: 3 }}>
              +${PORTFOLIO.pnl.toFixed(2)} / +{PORTFOLIO.pnlPct.toFixed(2)}%
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, marginBottom: 8 }}>
            <StatCard label="CASH" value={`$${PORTFOLIO.cash.toFixed(2)}`} />
            <StatCard label="EXPOSURE" value={`$${PORTFOLIO.exposure.toFixed(2)}`} sub={`${PORTFOLIO.exposurePct.toFixed(1)}%`} />
          </div>

          <Sparkline data={PNL_HISTORY} />

          <SectionLabel style={{ marginTop: 12 }}>POSITIONS</SectionLabel>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {['CONTRACT', 'DIR', 'SIZE', 'P&L'].map(h => (
                  <th key={h} style={{ ...S.condensed, fontSize: 8, color: S.t3, letterSpacing: '0.08em', textAlign: 'left', padding: '4px 4px', borderBottom: `1px solid ${S.border}` }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {POSITIONS.map((p, i) => (
                <tr key={i}>
                  <td style={{ ...S.mono, fontSize: 9, color: S.t2, padding: '4px 4px' }}>{p.id}</td>
                  <td style={{ ...S.mono, fontSize: 9, color: p.dir === 'YES' ? S.amber : S.blue, padding: '4px 4px', fontWeight: 600 }}>{p.dir}</td>
                  <td style={{ ...S.mono, fontSize: 9, color: S.t2, padding: '4px 4px' }}>${p.size.toFixed(2)}</td>
                  <td style={{ ...S.mono, fontSize: 9, color: p.pnl >= 0 ? S.amber : S.rose, padding: '4px 4px' }}>+${p.pnl.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <SectionLabel style={{ marginTop: 14 }}>CALIBRATION</SectionLabel>
          <CalibrationChart data={CALIBRATION} />
        </div>

        {/* ── CENTER PANEL ───────────────────────────────── */}
        <div style={{ background: S.bg, padding: 12, overflowY: 'auto' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, borderBottom: `1px solid ${S.border}`, paddingBottom: 6 }}>
            <span style={{ ...S.condensed, fontSize: 11, fontWeight: 600, color: S.t3, letterSpacing: '0.08em', textTransform: 'uppercase' }}>MARKETS</span>
            <span style={{ ...S.mono, fontSize: 9, color: S.t3, background: S.bg2, padding: '1px 6px' }}>12 markets</span>
          </div>

          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {['QUESTION', 'PRIOR', '', 'POSTERIOR', 'EDGE'].map((h, i) => (
                  <th key={i} style={{
                    ...S.condensed, fontSize: 8, color: S.t3, letterSpacing: '0.08em',
                    textAlign: i === 0 ? 'left' : 'right', padding: '5px 6px',
                    borderBottom: `1px solid ${S.border}`,
                    ...(i === 2 ? { width: '20%', textAlign: 'left' } : {}),
                    ...(i === 0 ? { width: '38%' } : {}),
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {MARKETS.map((m, i) => (
                <tr key={i} style={{ borderBottom: `1px solid rgba(255,255,255,0.03)` }}>
                  <td style={{ ...S.mono, fontSize: 10, color: S.t2, padding: '6px 6px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 280 }}>{m.q}</td>
                  <td style={{ ...S.mono, fontSize: 10, color: S.t2, padding: '6px 6px', textAlign: 'right' }}>{m.prior.toFixed(1)}%</td>
                  <td style={{ padding: '6px 6px' }}>
                    <div style={{ height: 4, background: 'rgba(255,255,255,0.04)', position: 'relative', width: '100%' }}>
                      <div style={{
                        height: '100%', width: `${m.posterior}%`,
                        background: m.edge >= 0 ? 'rgba(245,166,35,0.35)' : 'rgba(196,115,122,0.3)',
                      }} />
                    </div>
                  </td>
                  <td style={{ ...S.mono, fontSize: 10, color: S.t1, padding: '6px 6px', textAlign: 'right', fontWeight: 600 }}>{m.posterior.toFixed(1)}%</td>
                  <td style={{
                    ...S.mono, fontSize: 10, fontWeight: 600, padding: '6px 6px', textAlign: 'right',
                    color: m.edge >= 0 ? S.amber : S.rose,
                  }}>
                    {m.edge >= 0 ? '+' : ''}{m.edge.toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <SectionLabel style={{ marginTop: 16 }}>RADAR</SectionLabel>
          <div style={{ background: S.bg2, border: `1px solid ${S.border}`, padding: 8 }}>
            <RadarChart labels={RADAR_LABELS} values={RADAR_VALUES} size={260} />
          </div>
        </div>

        {/* ── RIGHT PANEL ────────────────────────────────── */}
        <div style={{ background: S.bg, padding: 12, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <SectionLabel>ACTIVITY</SectionLabel>
          <div style={{ flex: 1, overflowY: 'auto', marginBottom: 8 }}>
            {ACTIVITY.map((a, i) => (
              <div key={i} style={{
                padding: '3px 6px', fontSize: 10, ...S.mono, lineHeight: 1.5,
                borderLeft: `2px solid ${
                  a.kind === 'trade' ? S.amber :
                  a.kind === 'wiki' ? '#F59E0B' :
                  a.kind === 'cycle' ? 'rgba(255,255,255,0.08)' :
                  'rgba(0,212,255,0.2)'
                }`,
                color: a.kind === 'trade' ? S.amber : a.kind === 'wiki' ? '#F59E0B' : S.t2,
                marginBottom: 1,
              }}>
                <span style={{ color: S.t3, fontSize: 9, marginRight: 5 }}>{a.ts}</span>
                {a.msg}
              </div>
            ))}
          </div>

          <SectionLabel>NEWS</SectionLabel>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {NEWS.map((n, i) => (
              <div key={i} style={{
                padding: '6px 8px', background: S.bg2,
                border: `1px solid ${S.border}`, marginBottom: 2,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 3 }}>
                  <span style={{ ...S.condensed, fontSize: 8, fontWeight: 700, color: S.t3, letterSpacing: '0.06em' }}>{n.source}</span>
                  <span style={{
                    fontSize: 7, fontWeight: 700, letterSpacing: '0.08em', padding: '1px 4px',
                    color: n.priority === 'HIGH' ? S.amber : n.priority === 'MED' ? S.blue : S.t3,
                    background: n.priority === 'HIGH' ? 'rgba(245,166,35,0.1)' : n.priority === 'MED' ? 'rgba(0,212,255,0.08)' : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${n.priority === 'HIGH' ? 'rgba(245,166,35,0.15)' : n.priority === 'MED' ? 'rgba(0,212,255,0.12)' : 'rgba(255,255,255,0.06)'}`,
                    textTransform: 'uppercase',
                  }}>{n.priority}</span>
                  <span style={{ fontSize: 8, color: S.t3, marginLeft: 'auto' }}>{n.time}</span>
                </div>
                <div style={{ fontSize: 10, color: S.t2, lineHeight: 1.3, ...S.mono }}>{n.title}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Shared subcomponents ───────────────────────────────────────────────────

function SectionLabel({ children, style = {} }) {
  return (
    <div style={{
      ...S.condensed,
      fontSize: 10,
      fontWeight: 600,
      color: S.t3,
      letterSpacing: '0.1em',
      textTransform: 'uppercase',
      borderBottom: `1px solid ${S.border}`,
      paddingBottom: 5,
      marginBottom: 8,
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      ...style,
    }}>
      {children}
    </div>
  );
}

function StatCard({ label, value, sub }) {
  return (
    <div style={{ background: S.bg2, border: `1px solid ${S.border}`, padding: '8px 10px' }}>
      <div style={{ ...S.condensed, fontSize: 8, color: S.t3, letterSpacing: '0.08em', marginBottom: 2 }}>{label}</div>
      <div style={{ ...S.mono, fontSize: 15, fontWeight: 600, color: S.t1, lineHeight: 1.2 }}>{value}</div>
      {sub && <div style={{ ...S.mono, fontSize: 9, color: S.t3, marginTop: 1 }}>{sub}</div>}
    </div>
  );
}
