"""Single-sourced shared helpers for the signal-factory pipeline.

Every helper that was duplicated across crypto and sports scripts lives here.
Import-boundary invariant: this module is under predmarket/ and never imports
scripts/.  The engine + all family descriptors import from here.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ── Statistical helpers ──────────────────────────────────────────────────


def benjamini_hochberg(indexed_p_values: Sequence[tuple[int, float]]) -> dict[int, float]:
    """Benjamini-Hochberg step-up FDR q-value computation."""
    ordered = sorted(indexed_p_values, key=lambda item: item[1])
    count = len(ordered)
    output: dict[int, float] = {}
    running = 1.0
    for rank_from_end, (index, p_value) in enumerate(reversed(ordered), start=1):
        rank = count - rank_from_end + 1
        running = min(running, p_value * count / rank)
        output[index] = running
    return output


def binomial_survival(successes: int, trials: int, probability_null: float) -> float:
    """One-sided exact binomial survival P(X >= successes) under probability_null."""
    if trials <= 0 or successes < 0:
        return 1.0
    total = 0.0
    for k in range(successes, trials + 1):
        total += (
            math.comb(trials, k)
            * (probability_null**k)
            * ((1.0 - probability_null) ** (trials - k))
        )
    return min(max(total, 0.0), 1.0)


def wilson_lower_bound(wins: int, count: int, z: float) -> float:
    """Wilson score lower confidence bound."""
    if count <= 0:
        return 0.0
    p_hat = wins / count
    z2 = z * z
    denominator = 1 + z2 / count
    center = p_hat + z2 / (2 * count)
    margin = z * math.sqrt((p_hat * (1 - p_hat) + z2 / (4 * count)) / count)
    return max(0.0, min(1.0, (center - margin) / denominator))


# ── Data helpers (label / row processing) ────────────────────────────────


def chronological_split_index(count: int, test_fraction: float) -> int:
    """Return the split index for a chronological holdout.

    The first ``split_index`` rows are the training set; the remainder
    (latest ``test_fraction`` fraction) are the OOS holdout.
    """
    if count <= 0:
        return 0
    test_count = max(1, math.ceil(count * min(max(test_fraction, 0.0), 1.0)))
    return max(0, count - test_count)


def independent_contract_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeated observations by exact contract_ticker, keep earliest decision_time."""
    by_ticker: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("contract_ticker") or "")
        if not ticker:
            continue
        if ticker not in by_ticker or float(row.get("decision_ts") or 0) < float(
            by_ticker[ticker].get("decision_ts") or 0
        ):
            by_ticker[ticker] = dict(row)
    return sorted(
        by_ticker.values(), key=lambda item: (item["decision_ts"], item["contract_ticker"])
    )


def outcome_value(value: Any) -> int | None:
    """Normalize a settlement outcome to 0/1 or None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    number = probability(value)
    if number is not None:
        if number >= 0.999:
            return 1
        if number <= 0.001:
            return 0
    text = str(value).strip().lower()
    if text in {"yes", "true", "win", "1"}:
        return 1
    if text in {"no", "false", "loss", "0"}:
        return 0
    return None


# ── Cluster-control binary search ────────────────────────────────────────


def required_cluster_count(max_cluster_share: float, min_positive_clusters: int) -> int:
    """Minimum number of positive clusters needed to satisfy max_cluster_share."""
    if max_cluster_share <= 0:
        return max(1, min_positive_clusters)
    return max(min_positive_clusters, math.ceil(1 / max_cluster_share))


def controlled_cluster_costs(
    cluster_costs: Mapping[str, float], max_cluster_share: float
) -> dict[str, float]:
    """Binary-search controlled allocation across clusters under max_cluster_share.

    The search finds the largest total capacity T such that each cluster
    contributes at most max_cluster_share * T.  Returns per-cluster controlled
    costs (keys with zero controlled cost are omitted).
    """
    positive_costs = {key: value for key, value in cluster_costs.items() if value > 0}
    if not positive_costs or max_cluster_share <= 0:
        return {}
    total_available = sum(positive_costs.values())
    if total_available <= 0:
        return {}
    lo = 0.0
    hi = total_available
    for _ in range(80):
        mid = (lo + hi) / 2
        if (
            sum(min(cost, max_cluster_share * mid) for cost in positive_costs.values()) + 1e-9
            >= mid
        ):
            lo = mid
        else:
            hi = mid
    if lo <= 1e-9:
        return {}
    controlled = {
        key: min(cost, max_cluster_share * lo)
        for key, cost in positive_costs.items()
        if min(cost, max_cluster_share * lo) > 1e-9
    }
    return dict(sorted(controlled.items(), key=lambda item: (-item[1], item[0])))


# ── Cluster round-robin selection ────────────────────────────────────────


def select_cluster_round_robin(
    rows: Sequence[Mapping[str, Any]],
    *,
    cluster_key_field: str = "correlation_cluster_key",
    max_tickers: int,
) -> list[dict[str, Any]]:
    """Select candidates round-robin across clusters, then cap at max_tickers.

    Each cluster contributes one row per pass; within a cluster rows are
    ordered by candidate_sort_key (hours_to_close ascending, then identifiers).
    """
    limit = max(0, max_tickers)
    if limit <= 0:
        return []
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = str(row.get(cluster_key_field) or "unknown")
        clusters[key].append(dict(row))
    for cluster_rows in clusters.values():
        cluster_rows.sort(key=candidate_sort_key)
    cluster_keys = sorted(clusters, key=lambda key: (candidate_sort_key(clusters[key][0]), key))
    selected: list[dict[str, Any]] = []
    while len(selected) < limit and cluster_keys:
        next_keys: list[str] = []
        for key in cluster_keys:
            if len(selected) >= limit:
                next_keys.append(key)
                continue
            cluster_rows = clusters[key]
            if cluster_rows:
                selected.append(cluster_rows.pop(0))
            if cluster_rows:
                next_keys.append(key)
        cluster_keys = next_keys
    selected.sort(key=candidate_sort_key)
    return selected


def candidate_sort_key(row: Mapping[str, Any]) -> tuple[float, str, str, str]:
    """Default sort key for candidate rows within a cluster."""
    return (
        float(row.get("hours_to_close") or 999999.0),
        str(row.get("asset_symbol") or ""),
        str(row.get("contract_family") or ""),
        str(row.get("contract_ticker") or ""),
    )


# ── Numeric helpers ──────────────────────────────────────────────────────


def probability(value: Any) -> float | None:
    """Parse a value as a probability in [0, 1]."""
    number = optional_float(value)
    return number if number is not None and 0.0 <= number <= 1.0 else None


def optional_float(value: Any) -> float | None:
    """Safely convert a value to float, returning None on failure."""
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip().rstrip("%")
            if not value:
                return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def nonnegative_float(value: Any) -> float | None:
    """Safely convert a value to a non-negative float, returning None on failure."""
    number = optional_float(value)
    return number if number is not None and number >= 0 else None


def positive_number(value: Any) -> bool:
    number = optional_float(value)
    return number is not None and number > 0


def price_probability(value: Any) -> float | None:
    """Parse a price that may be a probability (0-1) or a percentage (0-100)."""
    number = probability(value)
    if number is not None:
        return number
    raw = nonnegative_float(value)
    if raw is not None and raw > 1.0 and raw <= 100.0:
        return raw / 100.0
    return None


def json_float(value: Any) -> float | None:
    """Round a float to 10 decimal places for JSON-safe comparison."""
    number = optional_float(value)
    return round(number, 10) if number is not None else None


# ── Timestamp helpers ────────────────────────────────────────────────────


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def timestamp(value: Any) -> float | None:
    """Parse a timestamp from int, float, or ISO-8601 string."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        number = None
    if number is not None:
        return number if math.isfinite(number) else None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def iso_from_timestamp(value: float | None) -> str | None:
    """Format a Unix timestamp as ISO-8601 UTC string."""
    if value is None:
        return None
    return datetime.fromtimestamp(value, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def iso_time(value: Any) -> str | None:
    """Parse and re-format a timestamp value as ISO-8601 UTC string, or return None."""
    ts = timestamp(value)
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def bucket_time(value: Any, *, resolution_minutes: int | None = None) -> str | None:
    """Format a timestamp value as a bucket string.

    When *resolution_minutes* is provided, rounds down to that resolution
    (e.g. 15 → :00/:15/:30/:45).  By default (None), returns the exact
    minute-level time (no rounding), matching the pre-engine crypto scripts.
    """
    ts = timestamp(value)
    if ts is None:
        return None
    parsed = datetime.fromtimestamp(ts, UTC)
    if resolution_minutes is not None:
        minute = (parsed.minute // resolution_minutes) * resolution_minutes
        parsed = parsed.replace(minute=minute, second=0, microsecond=0)
    return parsed.strftime("%Y-%m-%dT%H:%MZ")


# ── Statistics helpers ───────────────────────────────────────────────────


def mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


def counts(values: Sequence[Any]) -> dict[str, int]:
    """Return a Counter as a sorted dict (descending count, then key)."""
    counter = Counter(str(value if value is not None else "unknown") for value in values)
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


# ── Gate helpers ─────────────────────────────────────────────────────────


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def gate_counts(gates: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Aggregate gate statuses into {pass, warn, blocked, fail} counts."""
    counter = Counter(str(item.get("status") or "blocked") for item in gates)
    return {
        "pass": counter["pass"],
        "warn": counter["warn"],
        "blocked": counter["blocked"],
        "fail": counter["fail"],
    }


def gate_status(gates: Sequence[Mapping[str, Any]], name: str) -> str:
    for item in gates:
        if item.get("name") == name:
            return str(item.get("status") or "")
    return "blocked"


# ── IO / artifact helpers ────────────────────────────────────────────────


def read_json_or_empty(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def sha256_or_none(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_stamp(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum()) or "latest"


def mapping(value: Any) -> Mapping[str, Any]:
    """Cast to Mapping or return empty."""
    return value if isinstance(value, Mapping) else {}


# ── Safety / research helpers ────────────────────────────────────────────


def safety_flags(*, public_market_data_calls: bool = False) -> dict[str, bool]:
    return {
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": public_market_data_calls,
        "authenticated_api_calls": False,
        "provider_api_calls": public_market_data_calls,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "raw_payloads_copied_to_repo": False,
        "staking_or_sizing_guidance": False,
    }


def safe_research_artifact(value: Any) -> bool:
    """Check that an artifact dict has all research-only safety flags set."""
    if not isinstance(value, Mapping):
        return False
    s = value.get("safety") if isinstance(value.get("safety"), Mapping) else {}
    return (
        value.get("research_only") is True
        and value.get("execution_enabled") is False
        and value.get("market_execution") is not True
        and value.get("account_or_order_paths") is not True
        and s.get("market_execution") is False
        and s.get("account_or_order_paths") is False
        and s.get("database_writes") is False
    )


def outside_repo(path: Path, control_repo: Path) -> bool:
    """Return True if *path* resolves outside *control_repo*."""
    try:
        path.expanduser().resolve().relative_to(control_repo.resolve())
    except (ValueError, OSError):
        return True
    return False


def path_is_within(path: Path, root: Path) -> bool:
    """Return True if *path* resolves under *root*."""
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True
