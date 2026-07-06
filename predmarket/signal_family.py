"""SignalFamily descriptor type — the plug-in abstraction for the generic spine.

Every signal family (crypto, sports, weather, …) is a concrete instance of
this descriptor.  The generic pipeline stages in ``predmarket/engine.py`` take
a ``SignalFamily`` and dispatch all family-specific behavior through its fields.

Import-boundary invariant: this module is under ``predmarket/`` and NEVER
imports ``scripts/``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SignalFamily:
    """Descriptor that parameterizes the generic signal-factory spine.

    All family-specific behavior flows through these fields.  The spine
    never branches on ``family_id`` — it calls the field values directly.
    """

    # ── Identity ──────────────────────────────────────────────────────
    family_id: str
    """Unique key, e.g. ``"crypto_proxy"`` or ``"sports_baseball"``."""

    classification_tag: str | Sequence[str]
    """Universe-scan filter, e.g. ``"finance_crypto"`` or ``["KXMLBGAME", …]``."""

    official_settlement_source: str
    """Kalshi's documented settlement source, e.g. ``"CF Benchmarks RTI"``."""

    # ── Data sources ───────────────────────────────────────────────────
    reference_source_registry: Mapping[str, Any] = field(default_factory=dict)
    """Key → external feed mapping (e.g. asset→Coinbase product, or team→statsapi)."""

    fetcher: Callable[..., Any] | None = None
    """External fetch callable (injectable for tests; None means no fetch needed)."""

    # ── Feature / prediction / evaluation ──────────────────────────────
    feature_definitions: Mapping[str, Any] = field(default_factory=dict)
    """Computed-column definitions (schema or config for the family's features)."""

    prediction_rule: Callable[[Mapping[str, Any]], tuple[str | None, float | None]] | None = None
    """Callable(row) → (predicted_side in {"yes", "no"} | None, confidence).

    Returning ``None`` for side means "no prediction for this row".
    """

    model_evaluators: Sequence[Mapping[str, Any]] = field(default_factory=list)
    """Evaluator descriptors; each at minimum has a ``model_id`` and a callable
    that scores OOS rows using the family's ``prediction_rule``."""

    # ── Cluster key ────────────────────────────────────────────────────
    cluster_key_composer: Callable[[Mapping[str, Any]], str] | None = None
    """Callable(row) → opaque ``correlation_cluster_key`` string.

    Different families produce different key shapes (e.g. crypto:
    ``asset|family|close_bucket``; sports: ``league|game_winner|date``).
    """

    status_prefix: str = ""
    """Prefix used in status strings like ``crypto_proxy``, ``sports_proxy``, ``weather_proxy``.

    The engine's ``_falsification_status()`` uses this prefix to build
    family-scoped status strings.  Falls back to ``family_id`` when empty.
    """
