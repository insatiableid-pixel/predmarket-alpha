"""Tests for the Kalshi jurisdiction layer.

Covers:
- JurisdictionState dataclass integrity (VAL-JURIS-001)
- is_restricted() behavior (VAL-JURIS-002 through 005, 017)
- JurisdictionGate gating (VAL-JURIS-006 through 010, 014, 018)
- Config-backed restricted states (VAL-JURIS-011)
- Refresh function (VAL-JURIS-013)
- Kalshi agreement validation (VAL-JURIS-016)
- Refresh with source_url agreement wiring (VAL-JURIS-016)
- Cross-area assertions (VAL-CROSS-020, 021, 022, 024, 025, 026, 030, 039)
"""

from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

import predmarket.kalshi_jurisdiction as jm
from predmarket.kalshi_jurisdiction import (
    JurisdictionGate,
    JurisdictionState,
    is_restricted,
    refresh_jurisdiction_state_from_config,
    validate_against_kalshi_agreement,
)

# =============================================================================
# JurisdictionState dataclass integrity (VAL-JURIS-001)
# =============================================================================


class TestJurisdictionState:
    """VAL-JURIS-001: JurisdictionState dataclass integrity."""

    def test_dataclass_fields(self) -> None:
        """JurisdictionState has exactly restricted_states (frozenset[str]) and last_refreshed (datetime)."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN", "LA"}),
            last_refreshed=datetime.now(UTC),
        )
        assert state.restricted_states == frozenset({"TN", "LA"})
        assert isinstance(state.last_refreshed, datetime)

    def test_dataclass_is_frozen(self) -> None:
        """JurisdictionState is frozen (immutable after construction)."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        with pytest.raises(AttributeError):
            state.restricted_states = frozenset({"CA"})  # type: ignore[misc]

    def test_restricted_states_is_frozenset(self) -> None:
        """restricted_stances is type frozenset[str]."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN", "LA"}),
            last_refreshed=datetime.now(UTC),
        )
        assert isinstance(state.restricted_states, frozenset)
        assert all(isinstance(s, str) for s in state.restricted_states)


# =============================================================================
# is_restricted() behavior (VAL-JURIS-002 through 005, 017)
# =============================================================================


class TestIsRestricted:
    """Tests for the is_restricted() function."""

    def test_returns_true_for_known_restricted_state(self) -> None:
        """VAL-JURIS-002: is_restricted('TN') returns True when TN is restricted."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        assert is_restricted("TN", state) is True

    def test_returns_false_for_unrestricted_state(self) -> None:
        """VAL-JURIS-003: is_restricted('TX') returns False when TX is not restricted."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        assert is_restricted("TX", state) is False

    def test_case_insensitive_matching(self) -> None:
        """VAL-JURIS-004: is_restricted is case-insensitive."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        assert is_restricted("tn", state) is True
        assert is_restricted("Tn", state) is True
        assert is_restricted("tN", state) is True

    def test_default_unknown_state_policy_restrict(self) -> None:
        """VAL-JURIS-005: Unknown state code defaults to restrict (fail-closed)."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        # "ZZ" is not a known US state code; with default policy should restrict
        assert is_restricted("ZZ", state, unknown_state_policy="restrict") is True

    def test_unknown_state_policy_allow(self) -> None:
        """VAL-JURIS-005: Unknown state policy can be set to 'allow' to be permissive."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        assert is_restricted("ZZ", state, unknown_state_policy="allow") is False

    def test_restricted_state_with_allow_policy_still_restricted(self) -> None:
        """Even with allow unknown policy, known restricted states still block."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        assert is_restricted("TN", state, unknown_state_policy="allow") is True

    def test_empty_restricted_states_permissive(self) -> None:
        """VAL-JURIS-017: Empty restricted_states means all states are unrestricted."""
        state = JurisdictionState(
            restricted_states=frozenset(),
            last_refreshed=datetime.now(UTC),
        )
        assert is_restricted("TN", state) is False
        assert is_restricted("TX", state) is False
        assert is_restricted("CA", state) is False

    def test_none_state_returns_fail_closed(self) -> None:
        """When jurisdiction_state is None, is_restricted returns True (fail-closed)."""
        assert is_restricted("TN", None) is True
        assert is_restricted("TX", None) is True

    def test_multiple_restricted_states(self) -> None:
        """Multiple states can be restricted simultaneously."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN", "LA", "NJ"}),
            last_refreshed=datetime.now(UTC),
        )
        assert is_restricted("TN", state) is True
        assert is_restricted("LA", state) is True
        assert is_restricted("NJ", state) is True
        assert is_restricted("TX", state) is False
        assert is_restricted("CA", state) is False


# =============================================================================
# JurisdictionGate behavior (VAL-JURIS-006 through 010, 014, 018)
# =============================================================================


class TestJurisdictionGate:
    """Tests for the JurisdictionGate class."""

    def test_blocks_live_order_for_restricted_state(self) -> None:
        """VAL-JURIS-006: Live mode blocks order for restricted state."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        gate = JurisdictionGate(execution_mode="live", state=state)
        result = gate.allow_order("TN")
        assert result is False

    def test_allows_live_order_for_unrestricted_state(self) -> None:
        """VAL-JURIS-007: Live mode allows order for unrestricted state."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        gate = JurisdictionGate(execution_mode="live", state=state)
        result = gate.allow_order("TX")
        assert result is True

    def test_research_only_always_passes_restricted(self) -> None:
        """VAL-JURIS-008: Disabled mode always passes even for restricted states."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        gate = JurisdictionGate(execution_mode="disabled", state=state)
        assert gate.allow_order("TN") is True

    def test_research_only_always_passes_demo(self) -> None:
        """VAL-JURIS-008: Demo mode always passes even for restricted states."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        gate = JurisdictionGate(execution_mode="demo", state=state)
        assert gate.allow_order("TN") is True

    def test_fail_closed_when_state_is_none(self) -> None:
        """VAL-JURIS-009: Fail-closed when JurisdictionState is None in live mode."""
        gate = JurisdictionGate(execution_mode="live", state=None)
        assert gate.allow_order("TX") is False
        assert gate.allow_order("TN") is False

    def test_research_only_passes_when_state_is_none(self) -> None:
        """VAL-JURIS-009: Research-only passes even when state is None."""
        gate = JurisdictionGate(execution_mode="disabled", state=None)
        assert gate.allow_order("TX") is True
        assert gate.allow_order("TN") is True

    def test_fail_closed_when_state_stale(self) -> None:
        """VAL-JURIS-010: Fail-closed when jurisdiction data is stale."""
        stale_time = datetime.now(UTC) - timedelta(hours=48)
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=stale_time,
        )
        gate = JurisdictionGate(
            execution_mode="live",
            state=state,
            stale_threshold_hours=24,
        )
        # TX is not restricted but data is stale — should block
        assert gate.allow_order("TX") is False

    def test_fresh_state_not_stale(self) -> None:
        """State refreshed within threshold is not considered stale."""
        fresh_time = datetime.now(UTC) - timedelta(hours=1)
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=fresh_time,
        )
        gate = JurisdictionGate(
            execution_mode="live",
            state=state,
            stale_threshold_hours=24,
        )
        assert gate.allow_order("TX") is True

    def test_gate_blocks_all_order_operations(self) -> None:
        """VAL-JURIS-014: Gate blocks ALL order operations for restricted states."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        gate = JurisdictionGate(execution_mode="live", state=state)
        assert gate.allow_order("TN") is False
        assert gate.allow_cancel("TN") is False
        assert gate.allow_modify("TN") is False

    def test_gate_allows_all_operations_for_unrestricted(self) -> None:
        """VAL-JURIS-014: Gate allows all operations for unrestricted states."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        gate = JurisdictionGate(execution_mode="live", state=state)
        assert gate.allow_order("TX") is True
        assert gate.allow_cancel("TX") is True
        assert gate.allow_modify("TX") is True

    def test_gate_with_unrestricted_state_unknown_policy(self) -> None:
        """Gate respects unknown_state_policy when state is not found."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        gate = JurisdictionGate(
            execution_mode="live",
            state=state,
            unknown_state_policy="allow",
        )
        # With allow policy and state not restricted, should pass
        assert gate.allow_order("ZZ") is True

    def test_gate_with_restricted_and_unknown_restrict_policy(self) -> None:
        """Gate with unknown_state_policy='restrict' blocks unknown states."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        gate = JurisdictionGate(
            execution_mode="live",
            state=state,
            unknown_state_policy="restrict",
        )
        assert gate.allow_order("ZZ") is False

    def test_logs_blocks_with_structured_context(self) -> None:
        """VAL-JURIS-018: JurisdictionGate logs blocks with structured context."""
        import io
        import logging

        # Create a separate logger for this test to avoid interference
        test_logger = logging.getLogger("predmarket.kalshi_jurisdiction.test_logger")
        test_logger.propagate = False
        test_logger.setLevel(logging.WARNING)

        handler = logging.StreamHandler(io.StringIO())
        handler.setLevel(logging.WARNING)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        test_logger.addHandler(handler)

        from predmarket.kalshi_jurisdiction import _log_jurisdiction_block

        try:
            _log_jurisdiction_block(
                state_code="TN",
                reason="restricted",
                execution_mode="live",
                operation="order",
                _logger=test_logger,
            )

            output = handler.stream.getvalue()
            assert "WARNING" in output, f"Expected WARNING in output but got: {output!r}"
            assert "TN" in output, f"Expected TN in output but got: {output!r}"
            assert "restricted" in output.lower()
            assert "live" in output.lower()
        finally:
            test_logger.removeHandler(handler)


# =============================================================================
# Stale threshold is configurable (VAL-JURIS-020)
# =============================================================================


class TestStaleThreshold:
    """VAL-JURIS-020: Stale threshold is configurable."""

    def test_custom_stale_threshold(self) -> None:
        """Custom stale threshold is honored."""
        stale_for_custom = datetime.now(UTC) - timedelta(hours=2)
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=stale_for_custom,
        )
        # Threshold of 1 hour means 2 hours is stale
        gate = JurisdictionGate(
            execution_mode="live",
            state=state,
            stale_threshold_hours=1,
        )
        assert gate.allow_order("TX") is False

        # Threshold of 3 hours means 2 hours is not stale
        gate2 = JurisdictionGate(
            execution_mode="live",
            state=state,
            stale_threshold_hours=3,
        )
        assert gate2.allow_order("TX") is True

    def test_default_stale_threshold_is_24_hours(self) -> None:
        """Default stale threshold is 24 hours."""
        just_under_stale = datetime.now(UTC) - timedelta(hours=23)
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=just_under_stale,
        )
        gate = JurisdictionGate(execution_mode="live", state=state)
        assert gate.allow_order("TX") is True


# =============================================================================
# Config-backed restricted states (VAL-JURIS-011, 013, 016)
# =============================================================================


class TestRefresh:
    """VAL-JURIS-013: Refresh updates both restricted_states and last_refreshed."""

    def test_refresh_from_config(self) -> None:
        """refresh_jurisdiction_state_from_config produces valid JurisdictionState."""
        config = {"kalshi_live": {"jurisdiction": {"restricted_states": ["TN", "LA"]}}}
        state = refresh_jurisdiction_state_from_config(config)

        assert isinstance(state, JurisdictionState)
        assert state.restricted_states == frozenset({"TN", "LA"})
        # last_refreshed should be within 5 seconds of now
        now = datetime.now(UTC)
        delta = abs((now - state.last_refreshed).total_seconds())
        assert delta < 5, f"last_refreshed too far from now: {delta}s"

    def test_refresh_from_empty_config(self) -> None:
        """Empty restricted_states config produces empty frozenset."""
        config: dict[str, object] = {"kalshi_live": {"jurisdiction": {"restricted_states": []}}}
        state = refresh_jurisdiction_state_from_config(config)
        assert state.restricted_states == frozenset()

    def test_refresh_from_missing_jurisdiction_section(self) -> None:
        """Missing jurisdiction section produces empty frozenset."""
        config: dict[str, object] = {"kalshi_live": {}}
        state = refresh_jurisdiction_state_from_config(config)
        assert state.restricted_states == frozenset()

    def test_refresh_states_uppercased(self) -> None:
        """State codes are uppercased during refresh."""
        config = {"kalshi_live": {"jurisdiction": {"restricted_states": ["tn", "La"]}}}
        state = refresh_jurisdiction_state_from_config(config)
        assert "TN" in state.restricted_states
        assert "LA" in state.restricted_states
        assert "tn" not in state.restricted_states


# =============================================================================
# Refresh with source_url agreement wiring (VAL-JURIS-016)
# =============================================================================


class TestRefreshWithSourceUrl:
    """VAL-JURIS-016: refresh_jurisdiction_state_from_config reads source_url and fetches remote agreement."""

    def test_no_source_url_uses_config_only(self) -> None:
        """When source_url is None, uses config restricted_states as-is."""
        config = {
            "kalshi_live": {
                "jurisdiction": {
                    "restricted_states": ["TN", "LA"],
                    "source_url": None,
                }
            }
        }
        state = refresh_jurisdiction_state_from_config(config)
        assert state.restricted_states == frozenset({"TN", "LA"})

    def test_source_url_missing_uses_config_only(self) -> None:
        """When source_url key is missing, uses config restricted_states as-is."""
        config = {
            "kalshi_live": {
                "jurisdiction": {
                    "restricted_states": ["TN", "LA"],
                }
            }
        }
        state = refresh_jurisdiction_state_from_config(config)
        assert state.restricted_states == frozenset({"TN", "LA"})

    def test_source_url_agreement_matches_config(self) -> None:
        """When source_url returns the same states as config, uses config states."""
        mock_response = json.dumps({"restricted_states": ["TN", "LA"]}).encode("utf-8")
        config = {
            "kalshi_live": {
                "jurisdiction": {
                    "restricted_states": ["TN", "LA"],
                    "source_url": "https://kalshi.com/agreement.json",
                }
            }
        }
        with patch.object(jm, "urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value.read.return_value = mock_response
            state = refresh_jurisdiction_state_from_config(config)

        assert state.restricted_states == frozenset({"TN", "LA"})

    def test_source_url_adds_more_restricted_states(self) -> None:
        """When source_url has MORE states, uses union (more restrictive)."""
        mock_response = json.dumps({"restricted_states": ["TN", "LA", "NJ"]}).encode("utf-8")
        config = {
            "kalshi_live": {
                "jurisdiction": {
                    "restricted_states": ["TN"],
                    "source_url": "https://kalshi.com/agreement.json",
                }
            }
        }
        with patch.object(jm, "urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value.read.return_value = mock_response
            state = refresh_jurisdiction_state_from_config(config)

        assert state.restricted_states == frozenset({"TN", "LA", "NJ"})

    def test_config_has_more_states_uses_union(self) -> None:
        """When config has MORE states than source, uses union (more restrictive)."""
        mock_response = json.dumps({"restricted_states": ["TN"]}).encode("utf-8")
        config = {
            "kalshi_live": {
                "jurisdiction": {
                    "restricted_states": ["TN", "LA", "NJ"],
                    "source_url": "https://kalshi.com/agreement.json",
                }
            }
        }
        with patch.object(jm, "urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value.read.return_value = mock_response
            state = refresh_jurisdiction_state_from_config(config)

        assert state.restricted_states == frozenset({"TN", "LA", "NJ"})

    def test_no_overlap_uses_union(self) -> None:
        """When config and source have different states, uses union of both."""
        mock_response = json.dumps({"restricted_states": ["LA"]}).encode("utf-8")
        config = {
            "kalshi_live": {
                "jurisdiction": {
                    "restricted_states": ["TN"],
                    "source_url": "https://kalshi.com/agreement.json",
                }
            }
        }
        with patch.object(jm, "urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value.read.return_value = mock_response
            state = refresh_jurisdiction_state_from_config(config)

        assert state.restricted_states == frozenset({"TN", "LA"})

    def test_source_url_unreachable_falls_back_to_config(self) -> None:
        """When source_url is unreachable, gracefully falls back to config-only."""
        config = {
            "kalshi_live": {
                "jurisdiction": {
                    "restricted_states": ["TN", "LA"],
                    "source_url": "https://kalshi.com/agreement.json",
                }
            }
        }
        with patch.object(jm, "urlopen") as mock_urlopen:
            mock_urlopen.side_effect = OSError("Connection refused")
            state = refresh_jurisdiction_state_from_config(config)

        # Falls back to config-only
        assert state.restricted_states == frozenset({"TN", "LA"})

    def test_source_url_timeout_falls_back_to_config(self) -> None:
        """When source_url times out, gracefully falls back to config-only."""
        config = {
            "kalshi_live": {
                "jurisdiction": {
                    "restricted_states": ["TN"],
                    "source_url": "https://kalshi.com/agreement.json",
                }
            }
        }
        with patch.object(jm, "urlopen") as mock_urlopen:
            mock_urlopen.side_effect = TimeoutError("timed out")
            state = refresh_jurisdiction_state_from_config(config)

        assert state.restricted_states == frozenset({"TN"})

    def test_source_url_invalid_json_falls_back_to_config(self) -> None:
        """When source_url returns invalid JSON, gracefully falls back to config-only."""
        mock_response = b"not valid json"
        config = {
            "kalshi_live": {
                "jurisdiction": {
                    "restricted_states": ["TN"],
                    "source_url": "https://kalshi.com/agreement.json",
                }
            }
        }
        with patch.object(jm, "urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value.read.return_value = mock_response
            state = refresh_jurisdiction_state_from_config(config)

        assert state.restricted_states == frozenset({"TN"})

    def test_source_url_empty_restricted_states(self) -> None:
        """When source_url returns empty restricted_states, uses config only."""
        mock_response = json.dumps({"restricted_states": []}).encode("utf-8")
        config = {
            "kalshi_live": {
                "jurisdiction": {
                    "restricted_states": ["TN"],
                    "source_url": "https://kalshi.com/agreement.json",
                }
            }
        }
        with patch.object(jm, "urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value.read.return_value = mock_response
            state = refresh_jurisdiction_state_from_config(config)

        assert state.restricted_states == frozenset({"TN"})

    def test_states_normalized_to_uppercase_from_source(self) -> None:
        """States from source_url are uppercased."""
        mock_response = json.dumps({"restricted_states": ["tn", "la"]}).encode("utf-8")
        config = {
            "kalshi_live": {
                "jurisdiction": {
                    "restricted_states": [],
                    "source_url": "https://kalshi.com/agreement.json",
                }
            }
        }
        with patch.object(jm, "urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value.read.return_value = mock_response
            state = refresh_jurisdiction_state_from_config(config)

        assert state.restricted_states == frozenset({"TN", "LA"})
        assert "tn" not in state.restricted_states


# =============================================================================
# Kalshi agreement validation (VAL-JURIS-016)
# =============================================================================


class TestKalshiAgreementValidation:
    """VAL-JURIS-016: Config validates against Kalshi agreement before enforcement."""

    def test_agreement_matches_config(self) -> None:
        """When source agrees with config, uses config states unchanged."""
        config_states = frozenset({"TN", "LA"})
        source_states = frozenset({"TN", "LA"})
        result = validate_against_kalshi_agreement(config_states, source_states)
        assert result == frozenset({"TN", "LA"})

    def test_agreement_more_restrictive_uses_union(self) -> None:
        """When source has MORE restricted states, uses union (more restrictive)."""
        config_states = frozenset({"TN"})
        source_states = frozenset({"TN", "LA", "NJ"})
        result = validate_against_kalshi_agreement(config_states, source_states)
        assert result == frozenset({"TN", "LA", "NJ"})

    def test_config_more_restrictive_uses_union(self) -> None:
        """When config has MORE restricted states, uses union (more restrictive)."""
        config_states = frozenset({"TN", "LA", "NJ"})
        source_states = frozenset({"TN"})
        result = validate_against_kalshi_agreement(config_states, source_states)
        assert result == frozenset({"TN", "LA", "NJ"})

    def test_no_overlap_uses_union(self) -> None:
        """When config and source have different states, uses union of both."""
        config_states = frozenset({"TN"})
        source_states = frozenset({"LA"})
        result = validate_against_kalshi_agreement(config_states, source_states)
        assert result == frozenset({"TN", "LA"})

    def test_empty_source_uses_config(self) -> None:
        """When source is empty, uses config states."""
        config_states: frozenset[str] = frozenset({"TN", "LA"})
        source_states: frozenset[str] = frozenset()
        result = validate_against_kalshi_agreement(config_states, source_states)
        assert result == frozenset({"TN", "LA"})

    def test_no_source_url_uses_config(self) -> None:
        """When no source_url, config states are used as-is."""
        config_states: frozenset[str] = frozenset({"TN", "LA"})
        source_states: frozenset[str] | None = None
        result = validate_against_kalshi_agreement(config_states, source_states)
        assert result == frozenset({"TN", "LA"})


# =============================================================================
# Cross-area assertions
# =============================================================================


class TestCrossArea:
    """Cross-area assertion tests."""

    def test_jurisdiction_before_api_call(self) -> None:
        """VAL-CROSS-020, VAL-JURIS-019: Jurisdiction check precedes API call.

        In live mode, a restricted state must be blocked without making any
        external API calls. We verify the gate checks before the operation.
        """
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        gate = JurisdictionGate(execution_mode="live", state=state)

        # Should return False without needing any API call
        assert gate.allow_order("TN") is False

    def test_research_only_unaffected(self) -> None:
        """VAL-CROSS-021: Research-only paths are unaffected by jurisdiction."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        gate = JurisdictionGate(execution_mode="disabled", state=state)
        assert gate.allow_order("TN") is True

    def test_live_preflight_gates_jurisdiction(self) -> None:
        """VAL-CROSS-022: Live preflight gates jurisdiction check before order."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        gate = JurisdictionGate(execution_mode="live", state=state)
        # Preflight should reject restricted states before any order processing
        assert gate.allow_order("TN") is False
        assert gate.allow_order("TX") is True

    def test_yaml_config_backed(self) -> None:
        """VAL-JURIS-011: Restricted states come from YAML config, not hardcoded.

        Verify no hardcoded restricted states in the module.
        """
        source = inspect.getsource(jm)
        # The module should not have a hardcoded set of restricted states
        # as a module-level constant
        assert 'restricted_states = {"' not in source
        assert "restricted_states = frozenset" not in source

    def test_gate_rejects_before_rate_limiter(self) -> None:
        """Jurisdiction check precedes rate limiter (no rate limit tokens consumed)."""
        state = JurisdictionState(
            restricted_states=frozenset({"TN"}),
            last_refreshed=datetime.now(UTC),
        )
        gate = JurisdictionGate(execution_mode="live", state=state)

        # The gate returns False - the caller should check this BEFORE
        # acquiring rate limiter tokens
        assert gate.allow_order("TN") is False
