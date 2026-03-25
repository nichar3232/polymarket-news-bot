"""
Main autonomous agent loop.

Orchestrates all components:
  Data Ingestion → Signal Processing → Bayesian Fusion → Risk/Sizing → Execution

Starts two concurrent services:
  - The trading agent (main evaluation loop + background ingestion tasks)
  - The web dashboard server at http://localhost:8080
"""
from __future__ import annotations

import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

from config.settings import settings
from src.ingestion.polymarket import PolymarketClient, MarketInfo
from src.ingestion.rss import RSSMonitor, keyword_relevance_score
from src.ingestion.wikipedia import WikipediaEditMonitor
from src.signals.microstructure import MicrostructureAnalyzer
from src.signals.cross_market import CrossMarketAnalyzer
from src.signals.news_relevance import score_rss_item, NewsRelevanceScore
from src.signals.resolution import ResolutionMonitor
from src.reasoning.llm_client import LLMClient
from src.reasoning.decomposer import SuperforecasterDecomposer
from src.fusion.bayesian import BayesianFusion
from src.fusion.ensemble import EnsembleAggregator, MarketSignalBundle
from src.risk.kelly import compute_kelly
from src.risk.portfolio import PortfolioManager
from src.execution.paper import PaperTrader
from src.execution.orders import OrderRouter
from src.monitor.dashboard import Dashboard
from src.api.state import agent_state

import aiohttp


logger.remove()
logger.add(
    sys.stderr,
    level=settings.log_level,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:8s}</level> | {message}",
)


class PolymarketAgent:
    """
    Autonomous Polymarket trading agent.

    All state is shared with the web API via `agent_state` singleton so the
    dashboard reflects live data without any polling overhead.
    """

    def __init__(self) -> None:
        starting_capital = 1000.0
        self.portfolio = PortfolioManager(
            starting_value=starting_capital,
            max_exposure_pct=settings.max_portfolio_exposure,
            max_position_usd=settings.max_position_size_usd,
        )
        self.paper_trader = PaperTrader(self.portfolio)
        self.order_router = OrderRouter(
            paper_trader=self.paper_trader,
            trading_mode=settings.trading_mode,
        )

        self.bayesian = BayesianFusion()
        self.ensemble = EnsembleAggregator(self.bayesian)

        self.llm_client = LLMClient(
            groq_api_key=settings.groq_api_key,
            gemini_api_key=settings.gemini_api_key,
            ollama_base_url=settings.ollama_base_url,
            ollama_model=settings.ollama_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
        self.decomposer = SuperforecasterDecomposer(self.llm_client)
        self.dashboard = Dashboard(self.portfolio, settings.trading_mode)

        # Shared state — these are populated by background tasks and read by eval loop
        self._tracked_markets: list[MarketInfo] = []
        self._market_keywords: dict[str, list[str]] = {}
        self._news_buffer: list[tuple[str, object, float, float]] = []  # (market_id, item, score, ts)
        self._microstructure: dict[str, MicrostructureAnalyzer] = {}
        self._markets_ready = asyncio.Event()

        # Push initial state to API
        agent_state.trading_mode = settings.trading_mode
        agent_state.portfolio = self.portfolio.state

    async def _refresh_markets(self, client: PolymarketClient) -> None:
        markets = await client.get_markets(limit=200)
        markets.sort(key=lambda m: m.liquidity, reverse=True)
        self._tracked_markets = markets[:20]

        for m in self._tracked_markets:
            words = m.question.split()
            self._market_keywords[m.condition_id] = [
                w for w in words if len(w) > 4 and w.isalpha()
            ][:8]
            if m.condition_id not in self._microstructure:
                self._microstructure[m.condition_id] = MicrostructureAnalyzer()

        agent_state.tracked_markets = [
            {"id": m.condition_id, "question": m.question, "price_yes": m.price_yes}
            for m in self._tracked_markets
        ]
        logger.info(f"Tracking {len(self._tracked_markets)} markets")
        self._markets_ready.set()

    async def _rss_task(self) -> None:
        """Buffer relevant news for each tracked market."""
        monitor = RSSMonitor(poll_interval=60)
        async for batch in monitor.stream():
            # Wait until market keywords are available
            await self._markets_ready.wait()
            now = time.time()
            for item in batch:
                for market_id, keywords in self._market_keywords.items():
                    score = keyword_relevance_score(item, keywords)
                    if score > 0.1:
                        self._news_buffer.append((market_id, item, score, now))
            if len(self._news_buffer) > 1000:
                self._news_buffer = self._news_buffer[-1000:]

    async def _wikipedia_task(self) -> None:
        """Monitor Wikipedia edit velocity. Waits for markets to be ready first."""
        await self._markets_ready.wait()

        wiki_monitor = WikipediaEditMonitor()
        for keywords in self._market_keywords.values():
            wiki_monitor.register_keywords(keywords)

        async def on_spike(page: str, signal) -> None:
            msg = (
                f"Wikipedia spike: '{page}' — "
                f"{signal.edits_last_5min} edits/5min ({signal.velocity_score:.1f}x baseline)"
            )
            self.dashboard.log(msg)
            agent_state.push_event("wikipedia_spike", msg)

        await wiki_monitor.run(on_spike, poll_interval=120)

    def _build_news_context(self, market_news_items: list[tuple]) -> str:
        """Build a meaningful LLM context string from buffered news items."""
        lines = []
        for market_id, item, score, ts in market_news_items[-6:]:
            age_min = (time.time() - ts) / 60
            lines.append(f"[{age_min:.0f}min ago, relevance={score:.2f}] {item.title}: {item.summary[:120]}")
        return "\n".join(lines) if lines else "No recent relevant news available."

    async def _evaluate_market(
        self,
        session: aiohttp.ClientSession,
        client: PolymarketClient,
        market: MarketInfo,
        cross_market_analyzer: CrossMarketAnalyzer,
    ) -> None:
        market_id = market.condition_id
        keywords = self._market_keywords.get(market_id, [])
        prior_price = market.price_yes

        if prior_price <= 0.01 or prior_price >= 0.99:
            return  # Near-resolved markets have no actionable edge

        bundle = MarketSignalBundle(market_id=market_id, prior_price=prior_price)

        # --- Microstructure ---
        if market.yes_token_id:
            trades = await client.get_recent_trades(market.yes_token_id, limit=300)
            analyzer = self._microstructure[market_id]
            analyzer.add_trades(trades)
            bundle.vpin = analyzer.compute_vpin()

        # --- News (recency-weighted: drop signals older than 6 hours) ---
        now = time.time()
        fresh_news = [
            (mid, item, score, ts)
            for mid, item, score, ts in self._news_buffer
            if mid == market_id and now - ts < 21_600   # 6 hours
        ]
        bundle.news_scores = [
            score_rss_item(item, keywords, market.question)
            for _, item, _, _ in fresh_news[-10:]
        ]

        # --- Cross-market ---
        kalshi_price = None
        manifold_prob = None
        try:
            kalshi_markets = await cross_market_analyzer.fetch_kalshi_markets(
                session, " ".join(keywords[:3])
            )
            if kalshi_markets:
                ticker = kalshi_markets[0].get("ticker", "")
                if ticker:
                    kalshi_price = await cross_market_analyzer.fetch_kalshi_price(session, ticker)
        except Exception:
            pass

        try:
            manifold_markets = await cross_market_analyzer.search_manifold(
                session, " ".join(keywords[:3])
            )
            if manifold_markets:
                slug = manifold_markets[0].get("slug", "")
                if slug:
                    manifold_prob = await cross_market_analyzer.fetch_manifold_probability(session, slug)
        except Exception:
            pass

        bundle.cross_market = cross_market_analyzer.compute_signal(
            polymarket_price=prior_price,
            kalshi_price=kalshi_price,
            manifold_prob=manifold_prob,
        )

        # --- LLM decomposition ---
        news_context = self._build_news_context(fresh_news)
        cross_context = bundle.cross_market.notes if bundle.cross_market else ""
        try:
            bundle.llm_decomposition = await self.decomposer.decompose(
                question=market.question,
                resolution_criteria=market.description or market.question,
                current_market_price=prior_price,
                news_context=news_context,
                cross_market_context=cross_context,
            )
        except Exception as e:
            logger.debug(f"LLM decomposition failed for {market_id[:30]}: {e}")

        # --- Fuse ---
        result = self.ensemble.aggregate(bundle)
        self.dashboard.add_result(result)
        agent_state.push_result(result, market.question)

        # --- Trade if edge found ---
        if result.trade_direction != "NONE":
            self.dashboard.log(result.reasoning)

            # Price to pass to execution: YES price for YES trade, NO price for NO trade
            execution_price = prior_price if result.trade_direction == "YES" else (1 - prior_price)
            token_id = market.yes_token_id if result.trade_direction == "YES" else market.no_token_id

            kelly = compute_kelly(
                posterior_prob=result.posterior_prob,
                market_price_yes=prior_price,
                portfolio_value=self.portfolio.state.total_value,
                kelly_fraction=settings.kelly_fraction,
                max_position_pct=0.05,
                max_position_usd=settings.max_position_size_usd,
            )

            if kelly and kelly.is_positive:
                await self.order_router.execute(
                    market_id=market_id,
                    token_id=token_id,
                    kelly=kelly,
                    current_price=execution_price,
                )
                self.dashboard.log(kelly.describe())
                agent_state.push_event("trade", kelly.describe())
                agent_state.portfolio = self.portfolio.state
        else:
            logger.debug(
                f"{market_id[:30]}: no trade | prior={prior_price:.3f} "
                f"post={result.posterior_prob:.3f} eff_edge={result.effective_edge:+.3f}"
            )

    async def _main_loop(self) -> None:
        cross_market = CrossMarketAnalyzer()

        # Single shared session for all HTTP calls in the main loop
        async with aiohttp.ClientSession() as session:
            client = PolymarketClient(
                api_key=settings.polymarket_api_key,
                api_secret=settings.polymarket_api_secret,
                api_passphrase=settings.polymarket_api_passphrase,
            )
            client._session = session

            await self._refresh_markets(client)

            cycle = 0
            while True:
                t_start = time.monotonic()
                logger.info(f"--- Evaluation cycle {cycle} ---")
                agent_state.push_event("cycle", f"Cycle {cycle}: evaluating {len(self._tracked_markets)} markets")

                if cycle % 10 == 0 and cycle > 0:
                    await self._refresh_markets(client)

                tasks = [
                    self._evaluate_market(session, client, m, cross_market)
                    for m in self._tracked_markets
                ]
                await asyncio.gather(*tasks, return_exceptions=True)

                agent_state.portfolio = self.portfolio.state
                self.dashboard.update()
                self.dashboard.log(self.portfolio.get_summary().splitlines()[0])

                elapsed = time.monotonic() - t_start
                sleep = max(0, settings.signal_refresh_seconds - elapsed)
                cycle += 1
                await asyncio.sleep(sleep)

    async def run(self) -> None:
        self.dashboard.start_live()
        try:
            await asyncio.gather(
                self._main_loop(),
                self._rss_task(),
                self._wikipedia_task(),
                return_exceptions=True,
            )
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            self.dashboard.stop()
            self.paper_trader.print_summary()


def main() -> None:
    from src.api.server import start_api_server

    agent = PolymarketAgent()

    async def run_all() -> None:
        await asyncio.gather(
            agent.run(),
            start_api_server(),
        )

    try:
        asyncio.run(run_all())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
