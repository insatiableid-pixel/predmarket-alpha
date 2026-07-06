"""Decay-survival and retirement ledger for paper Kalshi signals."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from predmarket.paper_decision_engine import signal_key_for_row
from predmarket.shared_helpers import bucket_time, optional_float, read_json_or_empty, utc_now


def build_signal_decay_retirement_ledger(
    *,
    paper_decisions_path: Path,
    generated_utc: str | None = None,
    min_recent_decisions: int = 3,
    min_recent_accuracy: float = 0.5,
    max_calibration_error: float = 0.2,
) -> dict[str, Any]:
    payload = read_json_or_empty(Path(paper_decisions_path))
    rows = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    grouped = group_rows(rows)
    signals = [
        summarize_signal(
            signal_key,
            signal_rows,
            min_recent_decisions=min_recent_decisions,
            min_recent_accuracy=min_recent_accuracy,
            max_calibration_error=max_calibration_error,
        )
        for signal_key, signal_rows in sorted(grouped.items())
    ]
    retired_count = sum(1 for signal in signals if signal["retirement_status"] == "retired")
    return {
        "schema_version": 1,
        "generated_utc": generated_utc or utc_now(),
        "status": "signal_decay_retirement_ledger_ready"
        if signals
        else "signal_decay_retirement_ledger_empty",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "policy": {
            "min_recent_decisions": min_recent_decisions,
            "min_recent_accuracy": min_recent_accuracy,
            "max_calibration_error": max_calibration_error,
        },
        "summary": {
            "signal_count": len(signals),
            "retired_signal_count": retired_count,
            "active_signal_count": len(signals) - retired_count,
        },
        "signals": signals,
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
        },
    }


def group_rows(rows: Sequence[Any]) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        family_id = str(row.get("family_id") or "unknown_family")
        model_id = str(row.get("model_id") or "unknown_model")
        key = str(
            row.get("signal_key") or signal_key_for_row(row, family_id=family_id, model_id=model_id)
        )
        grouped[key].append(row)
    return grouped


def summarize_signal(
    signal_key: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    min_recent_decisions: int,
    min_recent_accuracy: float,
    max_calibration_error: float,
) -> dict[str, Any]:
    labeled = [row for row in rows if outcome(row) is not None and prediction(row) is not None]
    labeled.sort(key=lambda row: str(row.get("close_time") or row.get("decision_time") or ""))
    recent_bucket = latest_bucket(labeled)
    recent_rows = (
        [row for row in labeled if close_bucket(row) == recent_bucket] if recent_bucket else []
    )
    correct = sum(1 for row in labeled if outcome(row) == prediction(row))
    recent_correct = sum(1 for row in recent_rows if outcome(row) == prediction(row))
    calibration_error = mean_calibration_error(labeled)
    had_active_history = bool(labeled) or any(row.get("paper_usable") is True for row in rows)
    capacity_disappeared = had_active_history and all(
        (optional_float(row.get("capacity_estimate")) or 0.0) <= 0 for row in rows
    )
    reasons: list[str] = []

    # Decay-survival check: signals with too few recent labels OR low recent accuracy
    # are retired mechanically (VAL-DECAY-002). Zero-label signals remain active
    # (VAL-DECAY-007).
    has_labels = bool(labeled)
    if has_labels and recent_bucket is not None:
        recent_count = len(recent_rows)
        if recent_count < min_recent_decisions:
            reasons.append("decay_survival: insufficient recent labels")
        elif recent_correct / recent_count < min_recent_accuracy:
            reasons.append("decay_survival: recent bucket accuracy below threshold")

    # Calibration-drift check (VAL-DECAY-003)
    if calibration_error is not None and calibration_error > max_calibration_error:
        reasons.append("calibration_drift: calibration error above threshold")

    # Capacity disappearance is tracked but does NOT cause retirement on its
    # own (VAL-DECAY-008). Only retires when combined with another failure.
    if capacity_disappeared:
        reasons.append("capacity disappeared")

    # Only retire if at least one non-capacity reason exists (VAL-DECAY-008)
    non_capacity_reasons = [r for r in reasons if r not in ("capacity disappeared",)]
    status = "retired" if non_capacity_reasons else "active"
    return {
        "signal_key": signal_key,
        "retirement_status": status,
        "retirement_reasons": reasons,
        "label_count": len(labeled),
        "correct_count": correct,
        "accuracy": round(correct / len(labeled), 10) if labeled else None,
        "recent_bucket": recent_bucket,
        "recent_label_count": len(recent_rows),
        "recent_correct_count": recent_correct,
        "recent_accuracy": round(recent_correct / len(recent_rows), 10) if recent_rows else None,
        "mean_calibration_error": calibration_error,
        "capacity_disappeared": capacity_disappeared,
        "next_generator_action": "deprioritize_or_avoid" if status == "retired" else "eligible",
    }


def close_bucket(row: Mapping[str, Any]) -> str | None:
    return str(
        row.get("close_bucket")
        or bucket_time(row.get("close_time") or row.get("decision_time"))
        or ""
    )


def latest_bucket(rows: Sequence[Mapping[str, Any]]) -> str | None:
    buckets = [bucket for bucket in (close_bucket(row) for row in rows) if bucket]
    return max(buckets) if buckets else None


def prediction(row: Mapping[str, Any]) -> int | None:
    value = row.get("predicted_outcome")
    if value is None:
        side = str(row.get("side") or "").lower()
        value = 1 if side == "yes" else 0 if side == "no" else None
    return normalize_binary(value)


def outcome(row: Mapping[str, Any]) -> int | None:
    if "settled_outcome" in row:
        return normalize_binary(row.get("settled_outcome"))
    return normalize_binary(row.get("outcome"))


def normalize_binary(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    text = str(value).strip().lower()
    if text in {"1", "yes", "true", "win"}:
        return 1
    if text in {"0", "no", "false", "loss"}:
        return 0
    return None


def mean_calibration_error(rows: Sequence[Mapping[str, Any]]) -> float | None:
    errors: list[float] = []
    for row in rows:
        p = optional_float(row.get("calibrated_probability"))
        y = calibration_outcome(row)
        if p is None or y is None:
            continue
        errors.append(abs(p - y))
    return round(sum(errors) / len(errors), 10) if errors else None


def calibration_outcome(row: Mapping[str, Any]) -> int | None:
    selected = normalize_binary(row.get("selected_side_outcome"))
    if selected is not None:
        return selected
    y = outcome(row)
    pred = prediction(row)
    if y is None or pred is None:
        return None
    return int(y == pred)


def is_retired_signal(row: Mapping[str, Any], retirement_ledger: Mapping[str, Any]) -> bool:
    family_id = str(row.get("family_id") or "unknown_family")
    model_id = str(row.get("model_id") or "unknown_model")
    key = signal_key_for_row(row, family_id=family_id, model_id=model_id)
    signals = (
        retirement_ledger.get("signals")
        if isinstance(retirement_ledger.get("signals"), list)
        else []
    )
    return any(
        isinstance(signal, Mapping)
        and signal.get("signal_key") == key
        and signal.get("retirement_status") == "retired"
        for signal in signals
    )
