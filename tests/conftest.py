import pytest
import shutil
from pathlib import Path
from predmarket.config import Config, GlobalConfig, VenuesConfig, ForecastingConfig, PortfolioConfig

@pytest.fixture(autouse=True)
def setup_api_key_env(monkeypatch):
    monkeypatch.setenv("API_KEY", "predmarket_secret_key_123")

@pytest.fixture
def test_data_dir(tmp_path):
    # Create temporary data directory for tests to ensure no state pollution
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "raw").mkdir()
    (data_dir / "processed").mkdir()

    # Run Alembic migrations programmatically on the test database
    from alembic.config import Config as AlembicConfig
    from alembic import command

    db_path = data_dir / "database.sqlite"
    project_root = Path(__file__).resolve().parents[1]
    ini_path = project_root / "alembic.ini"
    alembic_cfg = AlembicConfig(str(ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_cfg, "head")

    yield data_dir
    shutil.rmtree(data_dir)

@pytest.fixture
def mock_config(test_data_dir):
    venues = VenuesConfig()
    venues.polymarket.enabled = False
    venues.polymarket.execution_enabled = False
    venues.polymarket.private_key = ""
    venues.polymarket.wallet_address = ""
    venues.kalshi.enabled = False
    venues.kalshi.execution_enabled = False
    venues.kalshi.api_key = ""
    venues.kalshi.api_secret = ""
    venues.interactive_brokers.enabled = False
    venues.interactive_brokers.execution_enabled = False

    return Config(
        global_cfg=GlobalConfig(
            environment="wsl2",
            data_dir=test_data_dir,
            log_level="DEBUG",
            dashboard_host="127.0.0.1",
            dashboard_port=9090
        ),
        venues=venues,
        forecasting=ForecastingConfig(),
        portfolio=PortfolioConfig()
    )
