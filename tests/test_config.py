from pathlib import Path

from predmarket.config import Config, load_config


def test_config_load_defaults():
    # Verify we can parse config.yaml successfully
    config = load_config()
    assert isinstance(config, Config)
    assert config.global_cfg.environment == "wsl2"
    assert config.global_cfg.data_dir == Path(__file__).resolve().parents[1] / "data"
    assert config.venues.polymarket.enabled is True
    assert config.portfolio.kelly.fraction == 0.25


def test_config_env_overrides(monkeypatch):
    # Test loading secrets from environment variables
    monkeypatch.setenv("KALSHI_USE_DEMO", "true")
    monkeypatch.setenv("KALSHI_API_KEY", "key-uuid-123")

    config = load_config()
    assert config.venues.kalshi.use_demo is True
    assert config.venues.kalshi.api_key == "key-uuid-123"
    assert (
        config.venues.kalshi.effective_api_url == "https://external-api.demo.kalshi.co/trade-api/v2"
    )
