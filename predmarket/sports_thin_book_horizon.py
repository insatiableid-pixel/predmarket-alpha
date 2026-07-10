"""Thin-book / depth-asymmetry fade family for sports executable horizons.

Distinct mechanism: temporary one-sided thin top-of-book liquidity is expected
to mean-revert under passive replenishment rather than continue (informed flow).
Research-only; uses fixed-horizon after-cost labels.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from predmarket.shared_helpers import json_float, optional_float

THIN_BOOK_FAMILY_ID = "sports_thin_book_fade_v1"


def attach_thin_book_features(labels: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in labels:
        item = dict(row)
        total = optional_float(row.get("total_depth_contracts"))
        spread = optional_float(row.get("yes_spread"))
        imbalance = optional_float(row.get("depth_imbalance_yes"))
        thinness = None
        if total is not None and total > 0:
            thinness = 1.0 / total
        abs_imbalance = abs(imbalance) if imbalance is not None else None
        thin_imbalance = None
        if thinness is not None and abs_imbalance is not None:
            thin_imbalance = thinness * abs_imbalance
        item["book_thinness"] = json_float(thinness)
        item["abs_depth_imbalance_yes"] = json_float(abs_imbalance)
        item["thin_imbalance_score"] = json_float(thin_imbalance)
        item["wide_spread_flag"] = (
            1.0 if spread is not None and spread >= 0.04 else 0.0 if spread is not None else None
        )
        fade_yes_pressure = None
        if imbalance is not None and thinness is not None:
            fade_yes_pressure = imbalance * thinness
        item["thin_book_fade_yes_pressure"] = json_float(fade_yes_pressure)
        output.append(item)
    return output


def thin_book_hypothesis_registry() -> list[dict[str, Any]]:
    return [
        {
            "model_id": "thin_imbalance_fade_yes_h900",
            "horizon_seconds": 900,
            "side": "no",
            "feature": "thin_book_fade_yes_pressure",
            "direction": "long_if_feature_gt",
            "threshold": 0.0005,
            "mechanism": "Thin YES-heavy books fade; buy NO for after-cost 15m reversion.",
            "negative_control": False,
            "feature_family": THIN_BOOK_FAMILY_ID,
        },
        {
            "model_id": "thin_imbalance_fade_no_h900",
            "horizon_seconds": 900,
            "side": "yes",
            "feature": "thin_book_fade_yes_pressure",
            "direction": "long_if_feature_lt",
            "threshold": -0.0005,
            "mechanism": "Thin NO-heavy books fade; buy YES for after-cost 15m reversion.",
            "negative_control": False,
            "feature_family": THIN_BOOK_FAMILY_ID,
        },
        {
            "model_id": "thin_imbalance_fade_yes_h300",
            "horizon_seconds": 300,
            "side": "no",
            "feature": "thin_book_fade_yes_pressure",
            "direction": "long_if_feature_gt",
            "threshold": 0.0003,
            "mechanism": "Thin YES-heavy books fade over 5m; buy NO after costs.",
            "negative_control": False,
            "feature_family": THIN_BOOK_FAMILY_ID,
        },
        {
            "model_id": "abs_imbalance_fade_no_h300",
            "horizon_seconds": 300,
            "side": "no",
            "feature": "abs_depth_imbalance_yes",
            "direction": "long_if_feature_gt",
            "threshold": 0.45,
            "mechanism": "Extreme absolute imbalance fades over 5m on the YES-heavy side.",
            "negative_control": False,
            "feature_family": THIN_BOOK_FAMILY_ID,
        },
        {
            "model_id": "abs_imbalance_fade_yes_h300",
            "horizon_seconds": 300,
            "side": "yes",
            "feature": "depth_imbalance_yes",
            "direction": "long_if_feature_lt",
            "threshold": -0.45,
            "mechanism": "Extreme negative imbalance fades over 5m toward YES.",
            "negative_control": False,
            "feature_family": THIN_BOOK_FAMILY_ID,
        },
        {
            "model_id": "negctrl_thin_momentum_h900",
            "horizon_seconds": 900,
            "side": "yes",
            "feature": "thin_book_fade_yes_pressure",
            "direction": "long_if_feature_gt",
            "threshold": 0.0005,
            "mechanism": "Negative control: follow thin YES pressure instead of fading it.",
            "negative_control": True,
            "feature_family": THIN_BOOK_FAMILY_ID,
        },
    ]
