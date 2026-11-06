from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment (see `.env.example`)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    kite_api_key: str = Field(default="YOUR_API_KEY", alias="KITE_API_KEY")
    kite_api_secret: str = Field(default="YOUR_API_SECRET", alias="KITE_API_SECRET")
    kite_redirect_url: str = Field(
        default="http://127.0.0.1:8000/callback/kite",
        alias="KITE_REDIRECT_URL",
    )
    kite_postback_secret: str | None = Field(default=None, alias="KITE_POSTBACK_SECRET")
    kite_login_url: str | None = Field(default=None, alias="KITE_LOGIN_URL")

    zerodha_user_id: str | None = Field(default=None, alias="ZERODHA_USER_ID")
    zerodha_password: str | None = Field(default=None, alias="ZERODHA_PASSWORD")
    kite_totp_secret: str | None = Field(default=None, alias="KITE_TOTP_SECRET")

    paper_trading: bool = Field(default=True, alias="PAPER_TRADING")
    enable_live_orders: bool = Field(default=False, alias="ENABLE_LIVE_ORDERS")

    max_daily_loss_inr: float = Field(default=5000.0, alias="MAX_DAILY_LOSS_INR")
    max_orders_per_day: int = Field(default=20, alias="MAX_ORDERS_PER_DAY")
    max_order_quantity: int = Field(default=1, alias="MAX_ORDER_QUANTITY")
    kill_switch_path: str = Field(default="/tmp/kite-starter-kill-switch", alias="KILL_SWITCH_PATH")

    order_tag_prefix: str = Field(default="ks", alias="ORDER_TAG_PREFIX")
    market_fallback_limit_buffer_pct: float = Field(default=0.15, alias="MARKET_FALLBACK_LIMIT_BUFFER_PCT")
    order_poll_interval_sec: float = Field(default=0.5, alias="ORDER_POLL_INTERVAL_SEC")
    order_poll_max_wait_sec: float = Field(default=45.0, alias="ORDER_POLL_MAX_WAIT_SEC")
    network_retry_attempts: int = Field(default=2, alias="NETWORK_RETRY_ATTEMPTS")
    network_retry_delay_sec: float = Field(default=0.75, alias="NETWORK_RETRY_DELAY_SEC")

    dashboard_user: str = Field(default="admin", alias="DASHBOARD_USER")
    dashboard_password: str = Field(default="change_me", alias="DASHBOARD_PASSWORD")

    database_path: str = Field(default="./data/kite_starter.db", alias="DATABASE_PATH")
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    strategy_instrument_token: int = Field(default=256265, alias="STRATEGY_INSTRUMENT_TOKEN")
    strategy_exchange: str = Field(default="NSE", alias="STRATEGY_EXCHANGE")
    strategy_tradingsymbol: str = Field(default="NIFTY 50", alias="STRATEGY_TRADINGSYMBOL")
    strategy_product: str = Field(default="MIS", alias="STRATEGY_PRODUCT")
    strategy_order_quantity: int = Field(default=1, alias="STRATEGY_ORDER_QUANTITY")
    strategy_bar_interval: str = Field(default="day", alias="STRATEGY_BAR_INTERVAL")
    ema_fast: int = Field(default=9, alias="EMA_FAST")
    ema_slow: int = Field(default=21, alias="EMA_SLOW")


def default_login_url(api_key: str) -> str:
    return f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3"
