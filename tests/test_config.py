import pytest
import os
from predmarket.config import load_config, Config

def test_config_load_defaults():
    # Verify we can parse config.yaml successfully
    config = load_config()
    assert isinstance(config, Config)
    assert config.global_cfg.environment == "wsl2"
    assert config.venues.polymarket.enabled is True
    assert config.portfolio.kelly.fraction == 0.25

def test_config_env_overrides(monkeypatch):
    # Test loading secrets from environment variables
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0xabc123")
    monkeypatch.setenv("KALSHI_API_KEY", "key-uuid-123")
    
    config = load_config()
    assert config.venues.polymarket.private_key == "0xabc123"
    assert config.venues.kalshi.api_key == "key-uuid-123"
