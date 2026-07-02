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
            self.api_secret = os.getenv("KALSHI_API_SECRET") or ""
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


class PortfolioConfig(BaseModel):
    kelly: KellyConfig = Field(default_factory=KellyConfig)
    risk_controls: RiskControlsConfig = Field(default_factory=RiskControlsConfig)


class Config(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    global_cfg: GlobalConfig = Field(default_factory=GlobalConfig, alias="global")
    venues: VenuesConfig = Field(default_factory=VenuesConfig)
    forecasting: ForecastingConfig = Field(default_factory=ForecastingConfig)
    portfolio: PortfolioConfig = Field(default_factory=PortfolioConfig)


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
