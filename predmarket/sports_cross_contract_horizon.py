"""Within-event cross-contract lead-lag features for sports executable horizons.

Distinct family from single-contract microstructure imbalance/momentum.
Research-only; uses the same after-cost fixed-horizon labels.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from predmarket.shared_helpers import json_float, optional_float, timestamp

CROSS_CONTRACT_FAMILY_ID = "sports_cross_contract_leadlag_v1"


def attach_cross_contract_features(
    labels: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Attach peer lead-lag features using same-event contemporaneous books."""
    by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    orphan: list[dict[str, Any]] = []
    for row in labels:
        item = dict(row)
        event = str(item.get("event_ticker") or "")
        if event:
            by_event[event].append(item)
        else:
            orphan.append(_empty_peer_features(item))

    output: list[dict[str, Any]] = []
    for event_rows in by_event.values():
        output.extend(_annotate_event_peers(event_rows))
    output.extend(orphan)
    return output


def _empty_peer_features(row: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["peer_contract_count"] = 0
    item["peer_mean_depth_imbalance_yes"] = None
    item["peer_self_imbalance_gap"] = None
    item["peer_max_depth_imbalance_delta"] = None
    item["peer_min_depth_imbalance_delta"] = None
    item["peer_mean_microprice_delta"] = None
    item["self_minus_peer_delta"] = None
    return item


def _peer_stats(peers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    imbalances = [
        optional_float(peer.get("depth_imbalance_yes"))
        for peer in peers
        if optional_float(peer.get("depth_imbalance_yes")) is not None
    ]
    deltas = [
        optional_float(peer.get("depth_imbalance_delta"))
        for peer in peers
        if optional_float(peer.get("depth_imbalance_delta")) is not None
    ]
    mps = [
        optional_float(peer.get("microprice_delta_from_previous"))
        for peer in peers
        if optional_float(peer.get("microprice_delta_from_previous")) is not None
    ]
    return {
        "peer_contract_count": len(peers),
        "peer_mean_depth_imbalance_yes": (
            sum(imbalances) / len(imbalances) if imbalances else None
        ),
        "peer_max_depth_imbalance_delta": max(deltas) if deltas else None,
        "peer_min_depth_imbalance_delta": min(deltas) if deltas else None,
        "peer_mean_microprice_delta": sum(mps) / len(mps) if mps else None,
    }


def _annotate_event_peers(event_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_time: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in event_rows:
        by_time[str(row.get("observed_at_utc") or "")].append(dict(row))
    ordered_times = sorted(
        (time_key for time_key in by_time if time_key),
        key=lambda value: timestamp(value) or 0.0,
    )
    history: list[dict[str, Any]] = []
    output: list[dict[str, Any]] = []
    for time_key in ordered_times:
        wave = by_time[time_key]
        for row in wave:
            peers = [
                peer
                for peer in wave
                if peer.get("contract_ticker") != row.get("contract_ticker")
            ]
            if not peers:
                peers = _prior_wave_peers(row, history)
            stats = _peer_stats(peers)
            self_imbalance = optional_float(row.get("depth_imbalance_yes"))
            self_delta = optional_float(row.get("depth_imbalance_delta"))
            peer_mean = stats["peer_mean_depth_imbalance_yes"]
            gap = None
            if peer_mean is not None and self_imbalance is not None:
                gap = peer_mean - self_imbalance
            peer_max_delta = stats["peer_max_depth_imbalance_delta"]
            row = dict(row)
            row["peer_contract_count"] = stats["peer_contract_count"]
            row["peer_mean_depth_imbalance_yes"] = json_float(peer_mean)
            row["peer_self_imbalance_gap"] = json_float(gap)
            row["peer_max_depth_imbalance_delta"] = json_float(peer_max_delta)
            row["peer_min_depth_imbalance_delta"] = json_float(
                stats["peer_min_depth_imbalance_delta"]
            )
            row["peer_mean_microprice_delta"] = json_float(
                stats["peer_mean_microprice_delta"]
            )
            row["self_minus_peer_delta"] = json_float(
                None
                if self_delta is None or peer_max_delta is None
                else self_delta - peer_max_delta
            )
            output.append(row)
        history.extend(wave)
    return output


def _prior_wave_peers(
    row: Mapping[str, Any], history: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    decision_ts = timestamp(row.get("observed_at_utc")) or 0.0
    recent_time = None
    peers: list[dict[str, Any]] = []
    for prior in reversed(list(history)):
        prior_ts = timestamp(prior.get("observed_at_utc")) or 0.0
        if prior_ts >= decision_ts:
            continue
        if prior.get("contract_ticker") == row.get("contract_ticker"):
            continue
        if recent_time is None:
            recent_time = prior.get("observed_at_utc")
        if prior.get("observed_at_utc") != recent_time:
            break
        peers.append(dict(prior))
    return peers


def cross_contract_hypothesis_registry() -> list[dict[str, Any]]:
    return [
        {
            "model_id": "peer_imbalance_gap_buy_yes_h300",
            "horizon_seconds": 300,
            "side": "yes",
            "feature": "peer_self_imbalance_gap",
            "direction": "long_if_feature_gt",
            "threshold": 0.20,
            "mechanism": "Peers on the same event show more YES pressure than self; self catches up.",
            "negative_control": False,
            "feature_family": CROSS_CONTRACT_FAMILY_ID,
            "min_peer_contracts": 1,
        },
        {
            "model_id": "peer_imbalance_gap_buy_no_h300",
            "horizon_seconds": 300,
            "side": "no",
            "feature": "peer_self_imbalance_gap",
            "direction": "long_if_feature_lt",
            "threshold": -0.20,
            "mechanism": "Peers show more NO pressure than self; self catches down.",
            "negative_control": False,
            "feature_family": CROSS_CONTRACT_FAMILY_ID,
            "min_peer_contracts": 1,
        },
        {
            "model_id": "peer_max_delta_follow_yes_h900",
            "horizon_seconds": 900,
            "side": "yes",
            "feature": "peer_max_depth_imbalance_delta",
            "direction": "long_if_feature_gt",
            "threshold": 0.08,
            "mechanism": "Largest sibling depth-delta increase leads follower YES demand over 15m.",
            "negative_control": False,
            "feature_family": CROSS_CONTRACT_FAMILY_ID,
            "min_peer_contracts": 1,
        },
        {
            "model_id": "peer_min_delta_follow_no_h900",
            "horizon_seconds": 900,
            "side": "no",
            "feature": "peer_min_depth_imbalance_delta",
            "direction": "long_if_feature_lt",
            "threshold": -0.08,
            "mechanism": "Largest sibling depth-delta decrease leads follower NO demand over 15m.",
            "negative_control": False,
            "feature_family": CROSS_CONTRACT_FAMILY_ID,
            "min_peer_contracts": 1,
        },
        {
            "model_id": "peer_microprice_lead_buy_yes_h300",
            "horizon_seconds": 300,
            "side": "yes",
            "feature": "peer_mean_microprice_delta",
            "direction": "long_if_feature_gt",
            "threshold": 0.004,
            "mechanism": "Peer microprice momentum leads related contract executable YES returns.",
            "negative_control": False,
            "feature_family": CROSS_CONTRACT_FAMILY_ID,
            "min_peer_contracts": 1,
        },
        {
            "model_id": "peer_microprice_lead_buy_no_h300",
            "horizon_seconds": 300,
            "side": "no",
            "feature": "peer_mean_microprice_delta",
            "direction": "long_if_feature_lt",
            "threshold": -0.004,
            "mechanism": "Peer microprice decline leads related contract executable NO returns.",
            "negative_control": False,
            "feature_family": CROSS_CONTRACT_FAMILY_ID,
            "min_peer_contracts": 1,
        },
        {
            "model_id": "negctrl_anti_peer_gap_h300",
            "horizon_seconds": 300,
            "side": "yes",
            "feature": "peer_self_imbalance_gap",
            "direction": "long_if_feature_lt",
            "threshold": -0.20,
            "mechanism": "Negative control: fade peer-lead gap instead of following it.",
            "negative_control": True,
            "feature_family": CROSS_CONTRACT_FAMILY_ID,
            "min_peer_contracts": 1,
        },
        {
            "model_id": "negctrl_random_peer_sign_h900",
            "horizon_seconds": 900,
            "side": "yes",
            "feature": "peer_max_depth_imbalance_delta",
            "direction": "long_if_feature_lt",
            "threshold": 0.0,
            "mechanism": "Negative control: trade against peer max delta sign.",
            "negative_control": True,
            "feature_family": CROSS_CONTRACT_FAMILY_ID,
            "min_peer_contracts": 1,
        },
    ]


def signal_fires_cross(row: Mapping[str, Any], spec: Mapping[str, Any]) -> bool:
    min_peers = int(spec.get("min_peer_contracts") or 0)
    if int(row.get("peer_contract_count") or 0) < min_peers:
        return False
    feature = optional_float(row.get(str(spec["feature"])))
    direction = str(spec["direction"])
    threshold = float(spec["threshold"])
    if feature is None:
        return False
    if direction == "long_if_feature_gt":
        return feature > threshold
    if direction == "long_if_feature_lt":
        return feature < threshold
    return False
