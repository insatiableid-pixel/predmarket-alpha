import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, model_validator

# Load env variables from .env if present
load_dotenv()


class GlobalConfig(BaseModel):
    environment: str = "wsl2"
    data_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1] / "data")
    log_level: str = "INFO"
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8050


class PolymarketConfig(BaseModel):
    """Polymarket is available for read-only market intelligence only."""

    enabled: bool = True
    clob_api_url: str = "https://clob.polymarket.com"
    min_liquidity_usd: float = 10000.0
    max_slippage_pct: float = 1.5


class KalshiConfig(BaseModel):
    enabled: bool = True
    execution_enabled: bool = False
    api_url: str = "https://external-api.kalshi.com/trade-api/v2"
    demo_api_url: str = "https://external-api.demo.kalshi.co/trade-api/v2"
    use_demo: bool = False
    api_key: str = Field(default="")
    api_secret: str = Field(default="")
    min_liquidity_usd: float = 10000.0
    max_slippage_pct: float = 1.0

    @model_validator(mode="after")
    def load_from_env(self) -> "KalshiConfig":
        if os.getenv("KALSHI_API_URL"):
            self.api_url = os.getenv("KALSHI_API_URL") or self.api_url
        if os.getenv("KALSHI_DEMO_API_URL"):
            self.demo_api_url = os.getenv("KALSHI_DEMO_API_URL") or self.demo_api_url
        if os.getenv("KALSHI_USE_DEMO") is not None:
            self.use_demo = (os.getenv("KALSHI_USE_DEMO") or "").lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        if not self.api_key:
            self.api_key = os.getenv("KALSHI_API_KEY") or ""
        if not self.api_secret:
            self.api_secret = (
                os.getenv("KALSHI_PRIVATE_KEY_PEM")
                or os.getenv("KALSHI_PRIVATE_KEY_PATH")
                or os.getenv("KALSHI_API_SECRET")
                or ""
            )
        return self

    @property
    def effective_api_url(self) -> str:
        return self.demo_api_url if self.use_demo else self.api_url


class VenuesConfig(BaseModel):
    polymarket: PolymarketConfig = Field(default_factory=PolymarketConfig)
    kalshi: KalshiConfig = Field(default_factory=KalshiConfig)


class EnsembleConfig(BaseModel):
    divergence_threshold: float = 0.15
    recency_anchor_threshold: float = 0.60
    nlp_damping_factor: float = 0.50
    min_forecast_prob: float = 0.01
    max_forecast_prob: float = 0.99


class ForecastingConfig(BaseModel):
    ensemble: EnsembleConfig = Field(default_factory=EnsembleConfig)


class KellyConfig(BaseModel):
    fraction: float = 0.25
    leverage_cap: float = 1.0
    min_edge: float = 0.03
    max_single_position_pct: float = 0.05
    max_correlated_exposure_pct: float = 0.10


class RiskControlsConfig(BaseModel):
    max_drawdown_limit: float = 0.20
    line_movement_threshold_pct: float = 0.05
    line_movement_window_mins: int = 30
    covariance_update_frequency_mins: int = 60


class RateLimitsConfig(BaseModel):
    public_rate: float = Field(default=30.0, ge=0.1)
    public_burst: float = Field(default=60.0, ge=1.0)
    auth_rate: float = Field(default=10.0, ge=0.1)
    auth_burst: float = Field(default=20.0, ge=1.0)


class JurisdictionConfig(BaseModel):
    restricted_states: list[str] = Field(default_factory=list)
    stale_threshold_hours: int = 24
    source_url: str | None = None
    unknown_state_policy: str = "restrict"


class KalshiLiveConfig(BaseModel):
    execution_mode: str = "disabled"
    execution_strategy: str = "maker_first"
    max_open_exposure_usd: float = 250.0
    max_per_contract_usd: float = 25.0
    max_per_family_usd: float = 100.0
    max_per_cluster_usd: float = 50.0
    max_daily_gross_buy_usd: float = 100.0
    max_daily_loss_usd: float = 50.0
    no_new_entry_seconds: int = 300
    passive_order_ttl_seconds: int = 180
    passive_price_improvement: float = 0.01
    unreconciled_order_timeout_seconds: int = 60
    max_orders_per_run: int = 5
    rate_limits: RateLimitsConfig = Field(default_factory=RateLimitsConfig)
    jurisdiction: JurisdictionConfig = Field(default_factory=JurisdictionConfig)

    @model_validator(mode="after")
    def load_from_env(self) -> "KalshiLiveConfig":
        if os.getenv("KALSHI_LIVE_EXECUTION_MODE"):
            self.execution_mode = os.getenv("KALSHI_LIVE_EXECUTION_MODE") or self.execution_mode
        if os.getenv("KALSHI_LIVE_EXECUTION_STRATEGY"):
            self.execution_strategy = (
                os.getenv("KALSHI_LIVE_EXECUTION_STRATEGY") or self.execution_strategy
            )
        numeric_envs = {
            "KALSHI_LIVE_MAX_OPEN_EXPOSURE_USD": "max_open_exposure_usd",
            "KALSHI_LIVE_MAX_PER_CONTRACT_USD": "max_per_contract_usd",
            "KALSHI_LIVE_MAX_PER_FAMILY_USD": "max_per_family_usd",
            "KALSHI_LIVE_MAX_PER_CLUSTER_USD": "max_per_cluster_usd",
            "KALSHI_LIVE_MAX_DAILY_GROSS_BUY_USD": "max_daily_gross_buy_usd",
            "KALSHI_LIVE_MAX_DAILY_LOSS_USD": "max_daily_loss_usd",
            "KALSHI_LIVE_PASSIVE_PRICE_IMPROVEMENT": "passive_price_improvement",
        }
        for env_name, field_name in numeric_envs.items():
            if os.getenv(env_name):
                setattr(self, field_name, float(os.getenv(env_name) or 0.0))
        int_envs = {
            "KALSHI_LIVE_NO_NEW_ENTRY_SECONDS": "no_new_entry_seconds",
            "KALSHI_LIVE_PASSIVE_ORDER_TTL_SECONDS": "passive_order_ttl_seconds",
            "KALSHI_LIVE_UNRECONCILED_ORDER_TIMEOUT_SECONDS": (
                "unreconciled_order_timeout_seconds"
            ),
            "KALSHI_LIVE_MAX_ORDERS_PER_RUN": "max_orders_per_run",
        }
        for env_name, field_name in int_envs.items():
            if os.getenv(env_name):
                setattr(self, field_name, int(os.getenv(env_name) or 0))
        return self


class PortfolioConfig(BaseModel):
    kelly: KellyConfig = Field(default_factory=KellyConfig)
    risk_controls: RiskControlsConfig = Field(default_factory=RiskControlsConfig)


class Config(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    global_cfg: GlobalConfig = Field(default_factory=GlobalConfig, alias="global")
    venues: VenuesConfig = Field(default_factory=VenuesConfig)
    forecasting: ForecastingConfig = Field(default_factory=ForecastingConfig)
    portfolio: PortfolioConfig = Field(default_factory=PortfolioConfig)
    kalshi_live: KalshiLiveConfig = Field(default_factory=KalshiLiveConfig)


def load_config(config_path: str | None = None) -> Config:
    project_root = Path(__file__).resolve().parents[1]
    if config_path is None:
        config_path = str(project_root / "config" / "config.yaml")

    path = Path(config_path)
    if not path.exists():
        fallback = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
        if fallback.exists():
            path = fallback
        else:
            raise FileNotFoundError(f"Configuration file not found at {config_path}")

    with open(path) as f:
        raw_yaml = yaml.safe_load(f) or {}

    config = Config.model_validate(raw_yaml)
    if not config.global_cfg.data_dir.is_absolute():
        config.global_cfg.data_dir = project_root / config.global_cfg.data_dir
    return config
