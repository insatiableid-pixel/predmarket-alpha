"""Core data contracts for research-grade forecasting.

These dataclasses are intentionally small and serializable. They define the
stable boundary between point-in-time data, forecasters, validation, and sizing.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Protocol

import numpy as np


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def monotone_quantiles(quantiles: Dict[float, float]) -> Dict[float, float]:
    """Return bounded, non-crossing quantiles keyed by probability level."""
    if not quantiles:
        return {}
    ordered = sorted((float(k), float(v)) for k, v in quantiles.items())
    values = np.clip([v for _, v in ordered], 0.0, 1.0)
    values = np.maximum.accumulate(values)
    return {q: float(v) for (q, _), v in zip(ordered, values)}


@dataclass
class SourceDocument:
    source_id: str
    source: str
    title: str
    url: str
    published_ts: float
    retrieved_ts: float
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate_as_of(self, as_of_ts: float) -> None:
        if self.published_ts > as_of_ts or self.retrieved_ts > as_of_ts:
            raise ValueError(
                f"source document {self.source_id} is after as_of_ts={as_of_ts}"
            )


@dataclass
class ForecastContext:
    event_id: str
    market_id: str
    as_of_ts: float
    category: str
    snapshot: Any
    market_history: List[float] = field(default_factory=list)
    orderbook: Dict[str, Any] = field(default_factory=dict)
    source_documents: List[SourceDocument] = field(default_factory=list)
    features: Dict[str, float] = field(default_factory=dict)

    def validate_point_in_time(self) -> None:
        for doc in self.source_documents:
            doc.validate_as_of(self.as_of_ts)


@dataclass
class ForecastDistribution:
    p_mean: float
    quantiles: Dict[float, float] = field(default_factory=dict)
    samples: Optional[List[float]] = None
    method: str = "unknown"
    model_version: str = "0"
    status_flags: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.p_mean = float(np.clip(self.p_mean, 0.0, 1.0))
        if self.samples is not None:
            self.samples = [float(np.clip(s, 0.0, 1.0)) for s in self.samples]
        self.quantiles = monotone_quantiles(self.quantiles)

    @classmethod
    def from_samples(
        cls,
        samples: List[float],
        method: str,
        model_version: str,
        evidence_refs: Optional[List[str]] = None,
        status_flags: Optional[List[str]] = None,
    ) -> "ForecastDistribution":
        arr = np.clip(np.asarray(samples, dtype=float), 0.0, 1.0)
        qs = [0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.975]
        quantiles = {q: float(np.quantile(arr, q)) for q in qs}
        return cls(
            p_mean=float(np.mean(arr)),
            quantiles=quantiles,
            samples=arr.tolist(),
            method=method,
            model_version=model_version,
            evidence_refs=evidence_refs or [],
            status_flags=status_flags or [],
        )


@dataclass
class ForecastRecord:
    event_id: str
    market_id: str
    as_of_ts: float
    horizon: str
    method: str
    model_version: str
    p_mean: float
    quantiles: Dict[float, float]
    density_samples_ref: str
    base_rate_ref: str
    evidence_refs: List[str]
    feature_hash: str
    calibration_bucket: str
    status_flags: List[str]
    forecast_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @classmethod
    def from_distribution(
        cls,
        *,
        event_id: str,
        market_id: str,
        as_of_ts: float,
        horizon: str,
        distribution: ForecastDistribution,
        features: Optional[Dict[str, Any]] = None,
        base_rate_ref: str = "",
        calibration_bucket: str = "",
    ) -> "ForecastRecord":
        samples_payload = distribution.samples or []
        return cls(
            event_id=event_id,
            market_id=market_id,
            as_of_ts=as_of_ts,
            horizon=horizon,
            method=distribution.method,
            model_version=distribution.model_version,
            p_mean=distribution.p_mean,
            quantiles=distribution.quantiles,
            density_samples_ref=stable_hash(samples_payload),
            base_rate_ref=base_rate_ref,
            evidence_refs=distribution.evidence_refs,
            feature_hash=stable_hash(features or {}),
            calibration_bucket=calibration_bucket,
            status_flags=distribution.status_flags,
        )

    def to_json_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["quantiles"] = {str(k): v for k, v in self.quantiles.items()}
        return payload


@dataclass
class EventSpec:
    event_id: str
    title: str
    category: str
    resolution_rules: Dict[str, Any]
    created_ts: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketLink:
    event_id: str
    venue: str
    market_id: str
    resolution_rules: Dict[str, Any]
    confidence: float
    linked_ts: float = field(default_factory=time.time)


class Forecaster(Protocol):
    name: str
    model_version: str

    def forecast(self, context: ForecastContext) -> ForecastDistribution:
        ...
