from predmarket.audit import AuditLogger
from predmarket.risk import RiskManager


def test_risk_drawdown_circuit_breaker(mock_config, test_data_dir, monkeypatch):
    audit = AuditLogger(str(test_data_dir))
    risk = RiskManager(mock_config, audit)

    # Empty history - no halt
    halted, dd = risk.check_drawdown_circuit_breaker()
    assert halted is False

    # Write peak equity
    audit.log_equity(10000.0)
    # Drawdown to 7500.0 (25% drawdown, exceeds 20% limit)
    audit.log_equity(7500.0)

    halted, dd = risk.check_drawdown_circuit_breaker()
    assert halted is True
    assert dd == 0.25

    # Test bypass with env var
    monkeypatch.setenv("OVERRIDE_DRAWDOWN_HALT", "true")
    halted, dd = risk.check_drawdown_circuit_breaker()
    assert halted is False


def test_risk_kelly_constrained_optimization(mock_config, test_data_dir):
    audit = AuditLogger(str(test_data_dir))
    risk = RiskManager(mock_config, audit)

    # Setup multiple correlated forecasts
    forecasts = [
        {
            "contract_id": "C-1",
            "title": "Legislation pass",
            "category": "political",
            "model_prob": 0.75,
            "market_implied": 0.50,  # High edge YES
            "status": "READY",
            "base_rate_reference": "Ref",
            "base_rate_prob": 0.28,
        },
        {
            "contract_id": "C-2",
            "title": "Nomination pass",
            "category": "political",
            "model_prob": 0.80,
            "market_implied": 0.45,  # High edge YES
            "status": "READY",
            "base_rate_reference": "Ref",
            "base_rate_prob": 0.28,
        },
    ]

    cash = 10000.0
    results = risk.optimize_portfolio_kelly(forecasts, cash)

    assert len(results) == 2
    for r in results:
        # Single position cap should limit allocation to max_single_position_pct (5% of bankroll = $500)
        assert r["recommended_fraction"] <= 0.05
        assert r["recommended_usd"] <= 500.0

    # Correlated exposure cap sum (both in 'political') should be <= max_correlated_exposure_pct (10% of bankroll = $1000)
    total_political_allocation = sum([r["recommended_usd"] for r in results])
    assert total_political_allocation <= 1000.0


def test_risk_marks_non_kalshi_forecasts_research_only(mock_config, test_data_dir):
    audit = AuditLogger(str(test_data_dir))
    risk = RiskManager(mock_config, audit)

    forecasts = [
        {
            "contract_id": "PM-1",
            "title": "Read-only context market",
            "venue": "Polymarket",
            "category": "political",
            "model_prob": 0.80,
            "market_implied": 0.40,
            "status": "READY",
            "base_rate_reference": "Ref",
            "base_rate_prob": 0.28,
        }
    ]

    results = risk.optimize_portfolio_kelly(forecasts, 10000.0)

    assert results[0]["status"] == "RESEARCH-ONLY"
    assert results[0]["recommended_fraction"] == 0.0
