"""Scored forecaster adapters for the research engine."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from predmarket.contracts import ForecastContext, ForecastDistribution, stable_hash


class LLMForecastOutput(BaseModel):
    """Structured LLM forecast payload parsed by the OpenAI SDK."""

    probability: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    uncertainty: float = Field(ge=0.0, le=1.0)
    base_rate_anchor: float = Field(ge=0.0, le=1.0)
    market_price_anchor: float = Field(ge=0.0, le=1.0)
    reasoning: str
    key_factors: list[str] = Field(default_factory=list)
    downside_factors: list[str] = Field(default_factory=list)
    cruxes: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


class LLMProbabilityCalibrator:
    """Simple Platt/temperature wrapper for LLM probabilities.

    Defaults are identity. Resolved forecasts can later update these parameters
    offline and pass them back into the forecaster without changing the API
    contract.
    """

    def __init__(
        self,
        temperature: float = 1.0,
        slope: float = 1.0,
        intercept: float = 0.0,
    ):
        self.temperature = max(float(temperature), 1e-6)
        self.slope = float(slope)
        self.intercept = float(intercept)

    def transform(self, probability: float) -> float:
        p = float(np.clip(probability, 1e-6, 1.0 - 1e-6))
        logit = np.log(p / (1.0 - p))
        adjusted = (self.slope * logit + self.intercept) / self.temperature
        return float(1.0 / (1.0 + np.exp(-adjusted)))


class MarketBaselineForecaster:
    name = "market_baseline"
    model_version = "1.0"

    def forecast(self, context: ForecastContext) -> ForecastDistribution:
        context.validate_point_in_time()
        snap = context.snapshot
        mid = float(getattr(snap, "mid", 0.5))
        spread = max(0.01, float(getattr(snap, "ask", mid) - getattr(snap, "bid", mid)))
        samples = np.clip(np.random.default_rng(17).normal(mid, spread, 501), 0.0, 1.0)
        return ForecastDistribution.from_samples(
            samples.tolist(),
            method=self.name,
            model_version=self.model_version,
            status_flags=["BASELINE"],
        )


class BaseRateResearchForecaster:
    name = "base_rate"
    model_version = "1.0"

    def __init__(self):
        from predmarket.signals import BaseRateModel

        self.base_rates = BaseRateModel()

    def forecast(self, context: ForecastContext) -> ForecastDistribution:
        context.validate_point_in_time()
        prob, ref_name, n = self.base_rates.get_base_rate(context.category)
        uncertainty = max(0.04, min(0.35, 1.0 / np.sqrt(max(n, 1))))
        samples = np.clip(np.random.default_rng(23).normal(prob, uncertainty, 501), 0.0, 1.0)
        return ForecastDistribution.from_samples(
            samples.tolist(),
            method=self.name,
            model_version=self.model_version,
            evidence_refs=[ref_name],
            status_flags=["BASE_RATE"],
        )


class FoundationTimeSeriesForecaster:
    """Adapter for TS foundation models with a deterministic fallback.

    The adapter forecasts market-implied probability paths, not event truth.
    If the optional foundation package is unavailable, it emits a research-only
    robust-trend forecast so the pipeline remains testable and explicit.
    """

    model_versions = {
        "chronos2": "chronos2-adapter-1.0",
        "timesfm25": "timesfm25-adapter-1.0",
    }

    def __init__(self, backbone: str = "chronos2"):
        if backbone not in self.model_versions:
            raise ValueError(f"unsupported foundation backbone: {backbone}")
        self.backbone = backbone
        self.name = f"foundation_{backbone}"
        self.model_version = self.model_versions[backbone]

    def forecast(self, context: ForecastContext) -> ForecastDistribution:
        context.validate_point_in_time()
        history = context.market_history or getattr(context.snapshot, "line_history", [])
        values = np.asarray(
            history if history else [getattr(context.snapshot, "mid", 0.5)], dtype=float
        )
        values = np.clip(values[np.isfinite(values)], 0.0, 1.0)
        if len(values) == 0:
            values = np.asarray([0.5])

        model_samples = self._try_model_forecast(values)
        if model_samples is None:
            model_samples = self._fallback_samples(values)
            flags = [f"{self.backbone.upper()}_UNAVAILABLE", "RESEARCH_ONLY"]
        else:
            flags = [self.backbone.upper()]
        return ForecastDistribution.from_samples(
            model_samples.tolist(),
            method=self.name,
            model_version=self.model_version,
            status_flags=flags,
        )

    def _try_model_forecast(self, values: np.ndarray) -> np.ndarray | None:
        if self.backbone == "chronos2":
            return None
        if self.backbone == "timesfm25":
            return None
        return None

    @staticmethod
    def _fallback_samples(values: np.ndarray) -> np.ndarray:
        current = float(values[-1])
        if len(values) >= 2:
            returns = np.diff(values)
            drift = float(np.median(returns[-10:]))
            vol = max(float(np.std(returns[-20:])), 0.015)
        else:
            drift = 0.0
            vol = 0.05
        center = np.clip(current + drift, 0.0, 1.0)
        rng = np.random.default_rng(31)
        return np.clip(rng.normal(center, vol, 501), 0.0, 1.0)


class LLMEvidenceForecaster:
    name = "llm_superforecaster"

    def __init__(
        self,
        api_key_env: str = "OPENAI_API_KEY",
        model: str | None = None,
        client: Any | None = None,
        calibrator: LLMProbabilityCalibrator | None = None,
        max_documents: int = 8,
    ):
        self.api_key_env = api_key_env
        self.model = model or os.getenv("OPENAI_FORECAST_MODEL", "gpt-5.5")
        self.model_version = f"openai-{self.model}"
        self.client = client
        self.calibrator = calibrator or LLMProbabilityCalibrator()
        self.max_documents = max_documents
        from predmarket.signals import BaseRateModel

        self.base_rates = BaseRateModel()

    def forecast(self, context: ForecastContext) -> ForecastDistribution:
        context.validate_point_in_time()
        if not os.getenv(self.api_key_env) and self.client is None:
            return ForecastDistribution(
                p_mean=0.5,
                quantiles={0.1: 0.25, 0.5: 0.5, 0.9: 0.75},
                method=self.name,
                model_version="disabled-1.0",
                status_flags=["LLM_DISABLED", "RESEARCH_ONLY"],
            )

        try:
            parsed = self._call_openai(context)
            return self._distribution_from_output(parsed, context)
        except Exception as exc:
            fallback = self._heuristic_forecast(context)
            fallback.status_flags.extend(["LLM_API_FAILED", type(exc).__name__, "RESEARCH_ONLY"])
            fallback.status_flags = sorted(set(fallback.status_flags))
            return fallback

    def _client(self) -> Any:
        if self.client is not None:
            return self.client
        try:
            from openai import OpenAI
        except Exception as exc:
            raise RuntimeError("OpenAI SDK is not installed") from exc
        return OpenAI(api_key=os.getenv(self.api_key_env))

    def _call_openai(self, context: ForecastContext) -> LLMForecastOutput:
        response = self._client().responses.parse(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": self._system_prompt(),
                },
                {
                    "role": "user",
                    "content": self._user_prompt(context),
                },
            ],
            text_format=LLMForecastOutput,
        )
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ValueError("OpenAI response did not include output_parsed")
        if isinstance(parsed, LLMForecastOutput):
            return parsed
        if isinstance(parsed, dict):
            return LLMForecastOutput.model_validate(parsed)
        return LLMForecastOutput.model_validate(parsed.model_dump())

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are a calibrated prediction-market forecaster. Produce only the "
            "requested structured forecast. Use base rates first, then update on "
            "market prices, dated evidence, liquidity, time-to-resolution, and "
            "known resolution semantics. Do not treat price movement as truth. "
            "Identify cruxes and contradictions. Never use information after the "
            "provided as_of timestamp."
        )

    def _user_prompt(self, context: ForecastContext) -> str:
        snap = context.snapshot
        base_rate, base_ref, n = self.base_rates.get_base_rate(context.category)
        as_of = datetime.fromtimestamp(context.as_of_ts, tz=UTC).isoformat()
        history = list(context.market_history or getattr(snap, "line_history", []) or [])
        docs = context.source_documents[: self.max_documents]
        doc_lines = []
        for doc in docs:
            published = datetime.fromtimestamp(doc.published_ts, tz=UTC).isoformat()
            excerpt = " ".join(doc.text.split())[:900]
            doc_lines.append(
                f"- id={doc.source_id} source={doc.source} published={published} "
                f"title={doc.title!r} url={doc.url} excerpt={excerpt!r}"
            )

        features = {
            key: float(value)
            for key, value in sorted(context.features.items())
            if isinstance(value, (int, float))
        }
        return "\n".join(
            [
                f"as_of_ts: {as_of}",
                f"event_id: {context.event_id}",
                f"market_id: {context.market_id}",
                f"category: {context.category}",
                f"title/question: {getattr(snap, 'title', '')}",
                "market:",
                f"  venue: {getattr(snap, 'venue', '')}",
                f"  bid: {float(getattr(snap, 'bid', 0.0)):.4f}",
                f"  ask: {float(getattr(snap, 'ask', 0.0)):.4f}",
                f"  mid: {float(getattr(snap, 'mid', 0.5)):.4f}",
                f"  volume_24h: {float(getattr(snap, 'volume_24h', 0.0)):.2f}",
                f"  open_interest: {float(getattr(snap, 'open_interest', 0.0)):.2f}",
                f"  history_tail: {history[-20:]}",
                "base_rate:",
                f"  probability: {base_rate:.4f}",
                f"  reference: {base_ref}",
                f"  sample_size: {n}",
                f"features_hash: {stable_hash(features)}",
                f"features: {features}",
                "dated_sources:",
                "\n".join(doc_lines) if doc_lines else "- none supplied",
                "Return a probability for the event resolving YES under the market's "
                "actual resolution rules. Put source ids or URLs used in citations.",
            ]
        )

    def _distribution_from_output(
        self, parsed: LLMForecastOutput, context: ForecastContext
    ) -> ForecastDistribution:
        calibrated = self.calibrator.transform(parsed.probability)
        spread = float(
            np.clip(
                0.04 + 0.28 * parsed.uncertainty + 0.18 * (1.0 - parsed.confidence),
                0.04,
                0.40,
            )
        )
        rng_seed = int(stable_hash({"p": calibrated, "m": context.market_id})[:8], 16)
        samples = np.clip(
            np.random.default_rng(rng_seed).normal(calibrated, spread, 501),
            0.0,
            1.0,
        )
        dist = ForecastDistribution.from_samples(
            samples.tolist(),
            method=self.name,
            model_version=self.model_version,
            evidence_refs=parsed.citations,
            status_flags=["LLM_API", "LLM_UNCALIBRATED", "RESEARCH_ONLY"],
        )
        dist.reasoning = parsed.reasoning
        dist.key_factors = parsed.key_factors
        dist.downside_factors = parsed.downside_factors
        dist.cruxes = parsed.cruxes
        dist.raw_probability = parsed.probability
        dist.calibrated_probability = calibrated
        dist.llm_confidence = parsed.confidence
        return dist

    def _heuristic_forecast(self, context: ForecastContext) -> ForecastDistribution:
        docs = context.source_documents[: self.max_documents]
        refs: list[str] = []
        positive = {"pass", "approve", "win", "surge", "beat", "agreement", "resolve"}
        negative = {"fail", "reject", "lose", "delay", "block", "miss", "veto"}
        score = 0
        for doc in docs:
            text = (doc.title + " " + doc.text[:500]).lower()
            score += sum(1 for token in positive if token in text)
            score -= sum(1 for token in negative if token in text)
            refs.append(doc.source_id)
        base_rate, _, _ = self.base_rates.get_base_rate(context.category)
        market = float(getattr(context.snapshot, "mid", 0.5))
        evidence_prob = float(1.0 / (1.0 + np.exp(-0.35 * score)))
        prob = float(np.clip(0.35 * base_rate + 0.45 * market + 0.20 * evidence_prob, 0.0, 1.0))
        samples = np.clip(np.random.default_rng(41).normal(prob, 0.18, 501), 0.0, 1.0)
        return ForecastDistribution.from_samples(
            samples.tolist(),
            method=self.name,
            model_version="evidence-heuristic-1.0",
            evidence_refs=refs,
            status_flags=["LLM_HEURISTIC", "RESEARCH_ONLY"],
        )


class ForecasterRegistry:
    def __init__(self):
        self._forecasters: dict[str, object] = {}

    def register(self, forecaster: object) -> None:
        name = forecaster.name
        self._forecasters[name] = forecaster

    def forecast_all(self, context: ForecastContext) -> dict[str, ForecastDistribution]:
        results = {}
        for name, forecaster in self._forecasters.items():
            results[name] = forecaster.forecast(context)
        return results

    @classmethod
    def default(cls) -> ForecasterRegistry:
        registry = cls()
        registry.register(MarketBaselineForecaster())
        registry.register(BaseRateResearchForecaster())
        registry.register(FoundationTimeSeriesForecaster("chronos2"))
        registry.register(FoundationTimeSeriesForecaster("timesfm25"))
        registry.register(LLMEvidenceForecaster())
        return registry
