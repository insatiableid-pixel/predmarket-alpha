import os
from pathlib import Path
from typing import Dict, Any, Optional
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from dotenv import load_dotenv

# Load env variables from .env if present
load_dotenv()

class GlobalConfig(BaseModel):
    environment: str = "wsl2"
    data_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1] / "data")
    log_level: str = "INFO"
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8050

class PolymarketConfig(BaseModel):
    enabled: bool = True
    execution_enabled: bool = False
    clob_api_url: str = "https://clob.polymarket.com"
    wallet_address: str = Field(default="")
    private_key: str = Field(default="")
    min_liquidity_usd: float = 10000.0
    max_slippage_pct: float = 1.5
    gas_reserve_matic: float = 10.0

    @model_validator(mode="after")
    def load_from_env(self) -> 'PolymarketConfig':
        if not self.private_key:
            self.private_key = os.getenv("POLYMARKET_PRIVATE_KEY") or ""
        if not self.wallet_address:
            self.wallet_address = os.getenv("POLYMARKET_WALLET_ADDRESS") or ""
        return self

class KalshiConfig(BaseModel):
    enabled: bool = True
    execution_enabled: bool = False
    api_url: str = "https://api.kalshi.co/v2"
    api_key: str = Field(default="")
    api_secret: str = Field(default="")
    min_liquidity_usd: float = 10000.0
    max_slippage_pct: float = 1.0

    @model_validator(mode="after")
    def load_from_env(self) -> 'KalshiConfig':
        if not self.api_key:
            self.api_key = os.getenv("KALSHI_API_KEY") or ""
        if not self.api_secret:
            self.api_secret = os.getenv("KALSHI_API_SECRET") or ""
        return self

class IBConfig(BaseModel):
    enabled: bool = True
    execution_enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 4002
    client_id: int = 10
    live_trading_enabled: bool = False
    live_confirmed: bool = Field(default=False)

    @model_validator(mode="after")
    def load_from_env(self) -> 'IBConfig':
        env_val = os.getenv("IB_LIVE_CONFIRMED", "false").lower()
        self.live_confirmed = env_val in ("true", "1", "yes")
        return self

class VenuesConfig(BaseModel):
    polymarket: PolymarketConfig = Field(default_factory=PolymarketConfig)
    kalshi: KalshiConfig = Field(default_factory=KalshiConfig)
    interactive_brokers: IBConfig = Field(default_factory=IBConfig)

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

def load_config(config_path: Optional[str] = None) -> Config:
    if config_path is None:
        project_root = Path(__file__).resolve().parents[1]
        config_path = str(project_root / "config" / "config.yaml")
    
    path = Path(config_path)
    if not path.exists():
        fallback = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
        if fallback.exists():
            path = fallback
        else:
            raise FileNotFoundError(f"Configuration file not found at {config_path}")
    
    with open(path, "r") as f:
        raw_yaml = yaml.safe_load(f) or {}

    return Config.model_validate(raw_yaml)

