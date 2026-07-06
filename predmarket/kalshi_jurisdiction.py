"""Kalshi jurisdiction layer — config-backed state restriction enforcement.

This module provides a jurisdiction gate that blocks live order operations for
users in restricted states. Research-only operations are never affected.

Components:
- JurisdictionState: Immutable dataclass holding restricted-states set and timestamp.
- is_restricted(): Pure function checking whether a state code is restricted.
- JurisdictionGate: Gating class that applies jurisdiction rules based on
  execution_mode (disabled/demo always passes; live checks restrictions).
- refresh_jurisdiction_state_from_config(): Loads restricted states from
  YAML-config-backed dictionary.
- validate_against_kalshi_agreement(): Diffs config against external source and
  returns the more restrictive set (union).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# Known US state and territory codes (50 states + DC + territories)
_KNOWN_US_STATE_CODES: frozenset[str] = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        "DC",
        "AS",
        "GU",
        "MP",
        "PR",
        "VI",
    }
)


def _is_state_code_known(code: str) -> bool:
    """Check if a state code matches a known US state or territory."""
    return code.upper() in _KNOWN_US_STATE_CODES


# ── JurisdictionState ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class JurisdictionState:
    """Immutable representation of current jurisdiction state.

    Attributes:
        restricted_states: Frozenset of two-letter state codes where trading
            is restricted (e.g., frozenset({"TN", "LA"})).
        last_refreshed: UTC timestamp of when this state was last refreshed.
    """

    restricted_states: frozenset[str]
    last_refreshed: datetime


# ── is_restricted ────────────────────────────────────────────────────────────


def is_restricted(
    state: str,
    jurisdiction_state: JurisdictionState | None,
    unknown_state_policy: str = "restrict",
) -> bool:
    """Check whether a state code is restricted.

    Falls back to fail-closed (returns True) when jurisdiction_state is None.
    Case-insensitive: normalizes input to uppercase before lookup.

    Args:
        state: Two-letter US state code (e.g., "TN", "tx").
        jurisdiction_state: Current jurisdiction state, or None if uninitialized.
        unknown_state_policy: What to do with unknown state codes.
            "restrict" (default) returns True for unknown codes (fail-closed).
            "allow" returns False for unknown codes.

    Returns:
        True if the state is restricted or fail-closed conditions apply.
    """
    if jurisdiction_state is None:
        return True

    normalized = state.upper().strip()

    if normalized in jurisdiction_state.restricted_states:
        return True

    # Unknown state code handling
    if not _is_state_code_known(normalized):
        if unknown_state_policy == "allow":
            return False
        return True  # default: restrict unknown codes

    return False


# ── JurisdictionGate ─────────────────────────────────────────────────────────


class JurisdictionGate:
    """Gates order operations based on jurisdiction state and execution mode.

    Research-only modes (disabled, demo) always pass. Live mode checks the
    state against the restricted list, with fail-closed on missing or stale data.

    Attributes:
        execution_mode: One of "disabled", "demo", or "live".
        state: Current JurisdictionState, or None if uninitialized.
        stale_threshold_hours: Max age of jurisdiction data before considered stale.
        unknown_state_policy: Policy for unknown state codes ("restrict" or "allow").
    """

    def __init__(
        self,
        execution_mode: str,
        state: JurisdictionState | None = None,
        stale_threshold_hours: int = 24,
        unknown_state_policy: str = "restrict",
    ) -> None:
        self._execution_mode = execution_mode.lower().strip()
        self._state = state
        self._stale_threshold_hours = stale_threshold_hours
        self._unknown_state_policy = unknown_state_policy

    @property
    def execution_mode(self) -> str:
        return self._execution_mode

    @property
    def state(self) -> JurisdictionState | None:
        return self._state

    @property
    def stale_threshold_hours(self) -> int:
        return self._stale_threshold_hours

    def _is_research_only(self) -> bool:
        """Return True if execution mode is research-only (disabled or demo)."""
        return self._execution_mode in {"disabled", "demo"}

    def _is_stale(self) -> bool:
        """Check if jurisdiction data is stale based on last_refreshed."""
        if self._state is None:
            return True
        age = datetime.now(UTC) - self._state.last_refreshed
        return age.total_seconds() > self._stale_threshold_hours * 3600

    def _check(self, state_code: str, operation: str) -> bool:
        """Core gating logic shared by all operation methods.

        Research-only always passes. Live mode fail-closed on missing/stale
        data, and blocks restricted states.

        Returns True if the operation is allowed, False if blocked.
        """
        # Research-only always passes
        if self._is_research_only():
            return True

        # Fail-closed: uninitialized
        if self._state is None:
            _log_jurisdiction_block(
                state_code=state_code,
                reason="uninitialized",
                execution_mode=self._execution_mode,
                operation=operation,
            )
            return False

        # Fail-closed: stale data
        if self._is_stale():
            _log_jurisdiction_block(
                state_code=state_code,
                reason="stale",
                execution_mode=self._execution_mode,
                operation=operation,
            )
            return False

        # Check if state is restricted
        blocked = is_restricted(
            state_code,
            self._state,
            unknown_state_policy=self._unknown_state_policy,
        )
        if blocked:
            _log_jurisdiction_block(
                state_code=state_code,
                reason="restricted",
                execution_mode=self._execution_mode,
                operation=operation,
            )
            return False

        return True

    def allow_order(self, state_code: str) -> bool:
        """Check if a new order is allowed for the given state code."""
        return self._check(state_code, "order")

    def allow_cancel(self, state_code: str) -> bool:
        """Check if a cancellation is allowed for the given state code."""
        return self._check(state_code, "cancel")

    def allow_modify(self, state_code: str) -> bool:
        """Check if a modification is allowed for the given state code."""
        return self._check(state_code, "modify")


# ── Structured Logging ────────────────────────────────────────────────────────


def _log_jurisdiction_block(
    state_code: str,
    reason: str,
    execution_mode: str,
    operation: str,
    _logger: logging.Logger | None = None,
) -> None:
    """Log a jurisdiction block with structured context.

    Args:
        state_code: Two-letter US state code.
        reason: Reason for the block (restricted, uninitialized, stale, unknown).
        execution_mode: Current execution mode (disabled, demo, live).
        operation: The blocked operation (order, cancel, modify).
        _logger: Override logger for testing. If None, uses module logger.
    """
    log = _logger or logger
    log.warning(
        "Jurisdiction block: state=%s reason=%s mode=%s operation=%s",
        state_code,
        reason,
        execution_mode,
        operation,
    )


# ── Fetch External Agreement ──────────────────────────────────────────────────


_FETCH_TIMEOUT_SECONDS: int = 15


def _fetch_restricted_states_from_url(
    source_url: str,
) -> frozenset[str] | None:
    """Fetch restricted states from an external URL (Kalshi published agreement).

    Attempts to parse the response as JSON with a ``restricted_states`` key
    containing a list of two-letter US state/territory codes. State codes are
    normalized to uppercase.

    Args:
        source_url: URL pointing to the published agreement JSON.

    Returns:
        Frozenset of restricted state codes, or None if the fetch or parse
        fails for any reason (network error, timeout, invalid JSON, etc.).
    """
    try:
        req = Request(source_url, headers={"User-Agent": "predmarket-alpha/1.0"})
        with urlopen(req, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
            body = resp.read()
        data = json.loads(body)
        raw_states = data.get("restricted_states")
        if not isinstance(raw_states, list):
            logger.warning(
                "Kalshi agreement fetch: response missing 'restricted_states' list at %s",
                source_url,
            )
            return None
        states = {
            s.upper().strip()
            for s in raw_states
            if isinstance(s, str) and s.strip()
        }
        return frozenset(states)
    except (json.JSONDecodeError, OSError, URLError, TimeoutError) as exc:
        logger.warning(
            "Kalshi agreement fetch failed for %s: %s — falling back to config-only list",
            source_url,
            exc,
        )
        return None


# ── Refresh ──────────────────────────────────────────────────────────────────


def _extract_source_url(config: dict[str, Any]) -> str | None:
    """Extract source_url from the jurisdiction config dict.

    Returns None if the key is missing, null, or not a string.
    """
    try:
        kalshi_live = config.get("kalshi_live", {})
        if isinstance(kalshi_live, dict):
            jurisdiction = kalshi_live.get("jurisdiction", {})
            if isinstance(jurisdiction, dict):
                raw = jurisdiction.get("source_url")
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
    except (AttributeError, TypeError):
        pass
    return None


def refresh_jurisdiction_state_from_config(config: dict[str, Any]) -> JurisdictionState:
    """Create a fresh JurisdictionState from a config dictionary.

    Reads the jurisdiction section under ``kalshi_live.jurisdiction`` from the
    config dict. When ``source_url`` is configured, fetches the remote Kalshi
    agreement and diffs it against the local config list, using the **union**
    (more restrictive) of both sets.

    Gracefully degrades to config-only if the remote source is unreachable or
    returns unparseable data.

    Args:
        config: Config dictionary (typically from YAML or pydantic model dump).

    Returns:
        A new JurisdictionState with current UTC timestamp.
    """
    restricted: list[str] = []
    try:
        kalshi_live = config.get("kalshi_live", {})
        if isinstance(kalshi_live, dict):
            jurisdiction = kalshi_live.get("jurisdiction", {})
            if isinstance(jurisdiction, dict):
                raw = jurisdiction.get("restricted_states", [])
                if isinstance(raw, list):
                    restricted = [
                        s.upper().strip() for s in raw if isinstance(s, str) and s.strip()
                    ]
    except (AttributeError, TypeError):
        pass

    config_states: frozenset[str] = frozenset(restricted)

    # Fetch external agreement if source_url is configured
    source_url = _extract_source_url(config)
    if source_url:
        source_states = _fetch_restricted_states_from_url(source_url)
        effective_states = validate_against_kalshi_agreement(config_states, source_states)
    else:
        effective_states = config_states

    return JurisdictionState(
        restricted_states=effective_states,
        last_refreshed=datetime.now(UTC),
    )


# ── Kalshi Agreement Validation ────────────────────────────────────────────────


def validate_against_kalshi_agreement(
    config_restricted_states: frozenset[str],
    source_restricted_states: frozenset[str] | None,
) -> frozenset[str]:
    """Validate config restricted states against a source (Kalshi agreement).

    If source is None or empty, uses config as-is.
    Otherwise, returns the union of config and source (more restrictive set).

    Args:
        config_restricted_states: States restricted per YAML config.
        source_restricted_states: States restricted per external source
            (e.g., Kalshi published agreement), or None if unavailable.

    Returns:
        The effective restricted states set (union if both available).
    """
    if source_restricted_states is None or not source_restricted_states:
        return config_restricted_states

    union = config_restricted_states | source_restricted_states
    if union != config_restricted_states:
        added = union - config_restricted_states
        logger.info(
            "Kalshi agreement validation: adding %d additional restricted states: %s",
            len(added),
            ", ".join(sorted(added)),
        )

    return union
