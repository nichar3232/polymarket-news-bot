from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Polymarket CLOB
    polymarket_api_key: str = ""
    polymarket_api_secret: str = ""
    polymarket_api_passphrase: str = ""
    polymarket_private_key: str = ""
    polymarket_funder_address: str = ""

    # Polygon network
    polygon_testnet: bool = True              # True = Amoy testnet, False = mainnet
    polygon_rpc_url: str = "https://rpc-amoy.polygon.technology"
    clob_host: str = "https://clob.polymarket.com"

    # LLM providers
    groq_api_key: str = ""
    gemini_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # News APIs
    newsapi_key: str = ""
    guardian_api_key: str = ""
    nytimes_api_key: str = ""

    # Reddit PRAW
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "polymarket-news-bot/0.1.0"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Trading mode: "paper" | "live" | "testnet"
    trading_mode: str = "paper"

    # Risk limits
    max_position_size_usd: float = 50.0
    max_portfolio_exposure: float = 0.25
    max_position_pct_per_trade: float = 0.05   # max single-position size as fraction of portfolio
    min_edge_threshold: float = 0.02
    kelly_fraction: float = 0.25

    # Agent behavior
    signal_refresh_seconds: int = 60
    llm_timeout_seconds: int = 30
    log_level: str = "INFO"

    @property
    def is_paper_trading(self) -> bool:
        return self.trading_mode == "paper"

    @property
    def is_testnet(self) -> bool:
        return self.trading_mode == "testnet" or self.polygon_testnet

    @property
    def chain_id(self) -> int:
        return 80002 if self.is_testnet else 137

    @property
    def has_groq(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def has_polymarket_creds(self) -> bool:
        # All 5 fields required by CLOB SDK — partial creds cause silent init failures (Bug 6 fix)
        return bool(
            self.polymarket_api_key
            and self.polymarket_api_secret
            and self.polymarket_api_passphrase
            and self.polymarket_private_key
            and self.polymarket_funder_address
        )


settings = Settings()
