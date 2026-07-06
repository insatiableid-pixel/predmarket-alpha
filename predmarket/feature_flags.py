"""Feature flag system for safe, incremental rollouts.

A lightweight, file-based feature flag system that reads flags from
environment variables and a local JSON config. Enables agents to ship
changes behind toggles without affecting all code paths immediately.

Usage::

    from predmarket.feature_flags import is_enabled, FeatureFlag

    if is_enabled(FeatureFlag.CRYPTO_PROXY_DECAY_MONITORING):
        run_decay_monitoring()

Flags default to ``False`` (disabled) and can be enabled via:
  1. Environment variable: ``FEATURE_CRYPTO_PROXY_DECAY_MONITORING=true``
  2. Local JSON config: ``config/feature_flags.json``
"""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path

_FLAGS_FILE = Path(__file__).resolve().parents[1] / "config" / "feature_flags.json"


class FeatureFlag(str, Enum):
    """Named feature flags. Add new flags here as the platform evolves."""

    CRYPTO_PROXY_DECAY_MONITORING = "crypto_proxy_decay_monitoring"
    CRYPTO_PROXY_ORDERBOOK_DEPTH = "crypto_proxy_orderbook_depth"
    TYPE2_REAL_TIME_MATCHER = "type2_real_time_matcher"
    EV_CALIBRATED_OVERLAY = "ev_calibrated_overlay"
    DASHBOARD_REAL_TIME = "dashboard_real_time"


def _load_json_flags() -> dict[str, bool]:
    """Load feature flags from the local JSON config file, if it exists."""
    try:
        if _FLAGS_FILE.exists():
            data = json.loads(_FLAGS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {k: bool(v) for k, v in data.items() if isinstance(v, (bool, int, str))}
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _env_flag_name(flag: str | FeatureFlag) -> str:
    """Convert a flag name to its environment variable name."""
    name = flag.value if isinstance(flag, FeatureFlag) else str(flag)
    return f"FEATURE_{name.upper()}"


def is_enabled(flag: str | FeatureFlag) -> bool:
    """Check whether a feature flag is enabled.

    Resolution order:
      1. Environment variable (``FEATURE_<NAME>=true``)
      2. Local JSON config (``config/feature_flags.json``)
      3. Default: ``False`` (disabled)

    All flags default to disabled. This ensures new code paths behind flags
    do not affect existing behavior until explicitly enabled.
    """
    flag_name = flag.value if isinstance(flag, FeatureFlag) else str(flag)
    env_var = _env_flag_name(flag)

    env_value = os.getenv(env_var, "").lower()
    if env_value in ("1", "true", "yes", "on"):
        return True
    if env_value in ("0", "false", "no", "off"):
        return False

    json_flags = _load_json_flags()
    return json_flags.get(flag_name, False)


def all_flags() -> dict[str, bool]:
    """Return the current state of all known feature flags."""
    return {flag.value: is_enabled(flag) for flag in FeatureFlag}


def enabled_flags() -> list[str]:
    """Return the names of all currently-enabled flags."""
    return [name for name, enabled in all_flags().items() if enabled]
