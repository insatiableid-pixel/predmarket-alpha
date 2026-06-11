import pytest
import shutil
from pathlib import Path
from predmarket.config import Config, GlobalConfig, VenuesConfig, ForecastingConfig, PortfolioConfig

@pytest.fixture
def test_data_dir(tmp_path):
    # Create temporary data directory for tests to ensure no state pollution
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "raw").mkdir()
    (data_dir / "processed").mkdir()
    yield data_dir
    shutil.rmtree(data_dir)

@pytest.fixture
def mock_config(test_data_dir):
    return Config(
        global_cfg=GlobalConfig(
            environment="wsl2",
            data_dir=test_data_dir,
            log_level="DEBUG",
            dashboard_host="127.0.0.1",
            dashboard_port=9090
        ),
        venues=VenuesConfig(),
        forecasting=ForecastingConfig(),
        portfolio=PortfolioConfig()
    )
