export const SIGNAL_DEFS: Record<string, { label: string; color: string; short: string }> = {
  microstructure_vpin:   { label: 'VPIN',           color: '#818cf8', short: 'VPIN' },
  microstructure_spread: { label: 'Spread / Depth', color: '#a78bfa', short: 'SPRD' },
  cross_market:          { label: 'Cross-Market',   color: '#e5b95e', short: 'XMKT' },
  news_rss:              { label: 'News (RSS)',      color: '#34d399', short: 'RSS' },
  news_gdelt:            { label: 'News (GDELT)',    color: '#5eead4', short: 'GDLT' },
  llm_decomposition:     { label: 'LLM Forecaster', color: '#f472b6', short: 'LLM' },
  wikipedia_velocity:    { label: 'Wikipedia',       color: '#e8915a', short: 'WIKI' },
  reddit_social:         { label: 'Reddit',          color: '#f47067', short: 'RDDT' },
}

export const SIGNAL_SOURCES = Object.keys(SIGNAL_DEFS)
