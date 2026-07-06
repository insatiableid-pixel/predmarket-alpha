"""Provider policy for sharp sports no-vig consensus inputs.

This module is intentionally read-only and data-plane only. It classifies local
provider observations so the sports consensus collector can tell the difference
between true anchor lines, exchange references, secondary offshore books, and
soft comparison books before any OOS/FDR or sizing work sees the rows.
"""

from __future__ import annotations

import csv
import hashlib
import json
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    display_name: str
    tier: str
    role: str
    provider_kind: str
    sports_strengths: tuple[str, ...]
    aliases: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class ProviderObservation:
    raw_provider: str
    provider_id: str
    source_id: str
    source_path: str | None
    source_kind: str
    sport: str | None
    market: str | None


ANCHOR_ROLES = frozenset({"a_plus_anchor", "anchor", "exchange_anchor"})
DEFAULT_PROVIDER_AUDIT_TARGET_SPORTS = ("mlb", "tennis", "soccer", "nfl", "nba")
SOCCER_ASIAN_SHARP_PROVIDERS = frozenset({"sbobet", "singbet", "ibc"})
NON_ACTIONABLE_COVERAGE_STATUSES = frozenset(
    {"deferred_no_current_rows", "deferred_no_compatible_current_market"}
)

PROVIDER_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        provider_id="pinnacle",
        display_name="Pinnacle",
        tier="A+",
        role="a_plus_anchor",
        provider_kind="sportsbook",
        sports_strengths=("tennis", "soccer", "mlb", "nfl", "nba", "nhl"),
        aliases=("pinnacle", "pinnacle sports", "pinnacle sportsbook", "pinny", "ps"),
        notes="Global sharp benchmark when timestamped access is available.",
    ),
    ProviderSpec(
        provider_id="circa",
        display_name="Circa",
        tier="A+",
        role="a_plus_anchor",
        provider_kind="sportsbook",
        sports_strengths=("nfl", "ncaaf", "mlb", "nba", "nhl"),
        aliases=("circa", "circa sports", "circasports"),
        notes="US-facing sharp book; especially valuable for major US sports.",
    ),
    ProviderSpec(
        provider_id="bookmaker",
        display_name="Bookmaker",
        tier="A",
        role="anchor",
        provider_kind="sportsbook",
        sports_strengths=("nfl", "ncaaf", "mlb", "nba", "nhl"),
        aliases=("bookmaker", "bookmaker.eu", "bookmaker eu"),
        notes="Old-school sharp screen; often grouped operationally with BetCRIS.",
    ),
    ProviderSpec(
        provider_id="betcris",
        display_name="BetCRIS",
        tier="A",
        role="anchor",
        provider_kind="sportsbook",
        sports_strengths=("nfl", "ncaaf", "soccer", "mlb", "nba"),
        aliases=("betcris", "cris", "betcris sportsbook"),
        notes="Sharp LatAm/offshore lineage; useful where legally and cleanly sourced.",
    ),
    ProviderSpec(
        provider_id="sbobet",
        display_name="SBOBet",
        tier="A",
        role="anchor",
        provider_kind="sportsbook",
        sports_strengths=("soccer", "asian_handicap"),
        aliases=("sbobet", "sbo", "sbo bet"),
        notes="Asian sharp reference, strongest for soccer and handicap markets.",
    ),
    ProviderSpec(
        provider_id="singbet",
        display_name="Singbet",
        tier="A",
        role="anchor",
        provider_kind="sportsbook",
        sports_strengths=("soccer", "asian_handicap"),
        aliases=("singbet", "sing bet", "crown"),
        notes="Asian sharp reference, strongest for soccer and handicap markets.",
    ),
    ProviderSpec(
        provider_id="ibc",
        display_name="IBC",
        tier="A",
        role="anchor",
        provider_kind="sportsbook",
        sports_strengths=("soccer", "asian_handicap"),
        aliases=("ibc", "ibcbet", "ibc bet"),
        notes="Asian sharp reference, strongest for soccer and handicap markets.",
    ),
    ProviderSpec(
        provider_id="betfair_exchange",
        display_name="Betfair Exchange",
        tier="A-exchange",
        role="exchange_anchor",
        provider_kind="exchange",
        sports_strengths=("tennis", "soccer", "horse_racing", "cricket"),
        aliases=(
            "betfair exchange",
            "betfair exchange uk",
            "betfair_ex_uk",
            "betfair_exchange",
            "betfair ex uk",
        ),
        notes="Exchange reference; must carry liquidity and commission caveats.",
    ),
    ProviderSpec(
        provider_id="matchbook",
        display_name="Matchbook",
        tier="A-exchange",
        role="exchange_anchor",
        provider_kind="exchange",
        sports_strengths=("tennis", "soccer"),
        aliases=("matchbook", "matchbook exchange"),
        notes="Exchange reference; useful when the market is liquid enough.",
    ),
    ProviderSpec(
        provider_id="smarkets",
        display_name="Smarkets",
        tier="A-exchange",
        role="exchange_anchor",
        provider_kind="exchange",
        sports_strengths=("tennis", "soccer"),
        aliases=("smarkets", "smarkets exchange"),
        notes="Exchange reference; useful when the market is liquid enough.",
    ),
    ProviderSpec(
        provider_id="lowvig",
        display_name="LowVig",
        tier="B",
        role="secondary",
        provider_kind="sportsbook",
        sports_strengths=("mlb", "nfl", "nba", "nhl"),
        aliases=("lowvig", "low vig"),
        notes="Accessible secondary line; not final sharp anchor by itself.",
    ),
    ProviderSpec(
        provider_id="betonlineag",
        display_name="BetOnline",
        tier="B",
        role="secondary",
        provider_kind="sportsbook",
        sports_strengths=("mlb", "nfl", "nba", "nhl"),
        aliases=("betonlineag", "betonline", "bet online"),
        notes="Accessible secondary line; not final sharp anchor by itself.",
    ),
    ProviderSpec(
        provider_id="draftkings",
        display_name="DraftKings",
        tier="C",
        role="comparison_only",
        provider_kind="sportsbook",
        sports_strengths=("us_soft_market",),
        aliases=("draftkings", "draft kings"),
        notes="Soft-book/retail line; use for lag diagnostics, not anchor consensus.",
    ),
    ProviderSpec(
        provider_id="fanduel",
        display_name="FanDuel",
        tier="C",
        role="comparison_only",
        provider_kind="sportsbook",
        sports_strengths=("us_soft_market",),
        aliases=("fanduel", "fan duel"),
        notes="Soft-book/retail line; use for lag diagnostics, not anchor consensus.",
    ),
    ProviderSpec(
        provider_id="betmgm",
        display_name="BetMGM",
        tier="C",
        role="comparison_only",
        provider_kind="sportsbook",
        sports_strengths=("us_soft_market",),
        aliases=("betmgm", "bet mgm"),
        notes="Soft-book/retail line; use for lag diagnostics, not anchor consensus.",
    ),
    ProviderSpec(
        provider_id="caesars",
        display_name="Caesars",
        tier="C",
        role="comparison_only",
        provider_kind="sportsbook",
        sports_strengths=("us_soft_market",),
        aliases=("caesars", "caesars sportsbook"),
        notes="Soft-book/retail line; use for lag diagnostics, not anchor consensus.",
    ),
    ProviderSpec(
        provider_id="betrivers",
        display_name="BetRivers",
        tier="C",
        role="comparison_only",
        provider_kind="sportsbook",
        sports_strengths=("us_soft_market",),
        aliases=("betrivers", "bet rivers"),
        notes="Soft-book/retail line; use for lag diagnostics, not anchor consensus.",
    ),
    ProviderSpec(
        provider_id="bovada",
        display_name="Bovada",
        tier="C",
        role="comparison_only",
        provider_kind="sportsbook",
        sports_strengths=("us_soft_market",),
        aliases=("bovada",),
        notes="Retail/offshore comparison line; do not use as final sharp anchor.",
    ),
    ProviderSpec(
        provider_id="betus",
        display_name="BetUS",
        tier="C",
        role="comparison_only",
        provider_kind="sportsbook",
        sports_strengths=("us_soft_market",),
        aliases=("betus", "bet us"),
        notes="Retail/offshore comparison line; do not use as final sharp anchor.",
    ),
    ProviderSpec(
        provider_id="mybookieag",
        display_name="MyBookie",
        tier="C",
        role="comparison_only",
        provider_kind="sportsbook",
        sports_strengths=("us_soft_market",),
        aliases=("mybookieag", "mybookie", "mybookie.ag"),
        notes="Retail/offshore comparison line; do not use as final sharp anchor.",
    ),
)


def _normalize_alias(value: Any) -> str:
    text = str(value or "").strip().lower()
    return " ".join(text.replace("_", " ").replace("-", " ").split())


_SPECS_BY_ID = {spec.provider_id: spec for spec in PROVIDER_SPECS}
_ALIASES = {
    _normalize_alias(alias): spec.provider_id
    for spec in PROVIDER_SPECS
    for alias in (spec.provider_id, spec.display_name, *spec.aliases)
}

PROVIDER_FIELDS = (
    "book_id",
    "sportsbook",
    "provider_key",
    "provider",
    "bookmaker",
    "bookmaker_key",
    "bookmaker_title",
)
SPORT_FIELDS = ("sport_key", "sport", "league")
MARKET_FIELDS = ("market_key", "market_type")


def normalize_provider_id(value: Any) -> str:
    """Return the canonical provider id when known, otherwise a safe slug."""
    text = _normalize_alias(value)
    if not text:
        return "unknown"
    return _ALIASES.get(text, text.replace(" ", "_"))


def provider_spec(provider_id: str) -> ProviderSpec | None:
    return _SPECS_BY_ID.get(normalize_provider_id(provider_id))


def is_anchor_provider(provider_id: str) -> bool:
    spec = provider_spec(provider_id)
    return bool(spec and spec.role in ANCHOR_ROLES)


def collect_provider_observations(
    payload: Any,
    *,
    source_id: str,
    source_path: Path | None = None,
    source_kind: str = "local_artifact",
) -> list[ProviderObservation]:
    observations: list[ProviderObservation] = []
    for row, inherited_sport, inherited_market in _walk_dicts_with_context(payload):
        observations.extend(
            _observations_from_row(
                row,
                source_id=source_id,
                source_path=source_path,
                source_kind=source_kind,
                inherited_sport=inherited_sport,
                inherited_market=inherited_market,
            )
        )
    return observations


def build_provider_audit(
    sources: Sequence[Mapping[str, Any]],
    *,
    run_id: str | None = None,
    created_ts: float | None = None,
    target_sports: Sequence[str] | None = None,
    deferred_sports: Sequence[str] | None = None,
    incompatible_market_sports: Sequence[str] | None = None,
) -> dict[str, Any]:
    ts = float(created_ts or time.time())
    observations = _source_observations(sources)
    provider_rows = _provider_rows(observations)
    strict_ids = _ids_for_source_kind(observations, "strict_consensus")
    donor_ids = _ids_for_source_kind(observations, "donor_consensus")
    raw_ids = _ids_for_source_kind(observations, "raw_provider_capture")
    sport_rows = _sport_coverage_rows(
        observations,
        target_sports=target_sports,
        deferred_sports=deferred_sports,
        incompatible_market_sports=incompatible_market_sports,
    )
    summary = _summary(provider_rows, strict_ids, donor_ids, raw_ids, sport_rows=sport_rows)
    gaps = _coverage_gaps(provider_rows, strict_ids, donor_ids, raw_ids, sport_rows=sport_rows)
    status = _status(provider_rows, strict_ids, donor_ids, raw_ids, sport_rows=sport_rows)
    return {
        "schema_version": 1,
        "run_id": run_id or _stable_run_id(sources),
        "created_ts": ts,
        "created_at_utc": datetime.fromtimestamp(ts, UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "raw_provider_payload_copied": False,
        "safety": {
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "account_or_order_paths": False,
            "market_execution": False,
            "raw_provider_payload_copied": False,
        },
        "policy": {
            "probability_source": "timestamp_matched_sharp_no_vig_consensus",
            "anchor_roles": sorted(ANCHOR_ROLES),
            "soft_books_policy": (
                "Retail/soft books may be lag-comparison features but cannot anchor "
                "sports consensus probability."
            ),
            "exchange_policy": (
                "Exchange prices require timestamp, liquidity, and commission/fee caveats "
                "before they can anchor consensus."
            ),
            "downstream_required_gates": [
                "exact_kalshi_mapping",
                "oos_falsification",
                "fdr_control",
                "cost_spread_replay",
                "capacity_depth",
                "correlation_cluster_control",
                "decay_survival",
            ],
            "target_sports": [row["sport"] for row in sport_rows],
            "deferred_target_sports": [
                row["sport"]
                for row in sport_rows
                if row.get("coverage_status") in NON_ACTIONABLE_COVERAGE_STATUSES
            ],
            "per_sport_coverage_rule": (
                "A sport is mature only when its strict consensus rows include at least two "
                "providers and at least one allowed sharp/exchange anchor for that sport."
            ),
            "deferred_coverage_rule": (
                "A target sport with no local current provider observations may be explicitly "
                "deferred by config, e.g. offseason/no-current-Kalshi-row surfaces. Deferred "
                "sports stay visible but are excluded from actionable provider-gap counts."
            ),
            "incompatible_market_rule": (
                "A target sport with sharp provider observations but no compatible current "
                "Kalshi contract type is non-actionable until a separate exact mapping/model "
                "surface is defined. Example: tennis h2h prices cannot price set-winner "
                "contracts."
            ),
        },
        "summary": summary,
        "provider_catalog": [asdict(spec) for spec in PROVIDER_SPECS],
        "providers": provider_rows,
        "sport_coverage": sport_rows,
        "coverage_gaps": gaps,
        "recommendations": _recommendations(gaps),
        "sources": _source_rows(sources),
    }


def render_provider_audit_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Sports Consensus Provider Audit",
        "",
        f"- Status: `{report.get('status')}`",
        "- Mode: research-only",
        "- Execution enabled: `false`",
        "- Provider/API calls: `false`",
        "",
        "## Summary",
        "",
        f"- Providers observed: `{summary.get('provider_count', 0)}`",
        f"- Strict consensus providers: `{summary.get('strict_consensus_provider_count', 0)}`",
        f"- Strict anchor providers: `{summary.get('strict_anchor_provider_count', 0)}`",
        f"- Donor anchor providers: `{summary.get('donor_anchor_provider_count', 0)}`",
        f"- Raw/local anchor providers: `{summary.get('raw_anchor_provider_count', 0)}`",
        f"- Target sports with strict consensus rows: `{summary.get('strict_consensus_sport_count', 0)}/{summary.get('sport_target_count', 0)}`",
        f"- Target sports covered: `{summary.get('sport_covered_count', 0)}/{summary.get('sport_target_count', 0)}`",
        f"- Target sports deferred: `{summary.get('sport_deferred_count', 0)}`",
        f"- Actionable sport gaps: `{summary.get('sport_gap_count', 0)}`",
        "",
        "## Sport Coverage",
        "",
    ]
    for row in report.get("sport_coverage", []):
        if isinstance(row, Mapping):
            lines.append(
                "- "
                f"`{row.get('sport')}` status `{row.get('coverage_status')}` "
                f"strict providers `{row.get('strict_provider_count')}` "
                f"strict anchors `{row.get('strict_anchor_provider_count')}` "
                f"providers `{', '.join(row.get('strict_providers', []))}`"
            )
    lines.extend(
        [
            "",
            "## Providers",
            "",
        ]
    )
    for row in report.get("providers", []):
        if isinstance(row, Mapping):
            lines.append(
                "- "
                f"`{row.get('provider_id')}` "
                f"tier `{row.get('tier')}` role `{row.get('role')}` "
                f"source_kinds `{', '.join(row.get('source_kinds', []))}` "
                f"observations `{row.get('observation_count')}`"
            )
    gaps = [gap for gap in report.get("coverage_gaps", []) if isinstance(gap, Mapping)]
    if gaps:
        lines.extend(["", "## Coverage Gaps", ""])
        for gap in gaps:
            lines.append(f"- `{gap.get('reason')}`: {gap.get('detail')}")
    recommendations = [row for row in report.get("recommendations", []) if isinstance(row, Mapping)]
    if recommendations:
        lines.extend(["", "## Recommendations", ""])
        for row in recommendations:
            lines.append(f"- `{row.get('priority')}`: {row.get('action')}")
    lines.extend(
        [
            "",
            "> Audit only. This artifact does not compute probabilities, stake, fees, orders, or live eligibility.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def provider_rows_to_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "provider_id",
        "display_name",
        "tier",
        "role",
        "provider_kind",
        "observation_count",
        "source_kinds",
        "sports",
        "markets",
        "consensus_anchor_allowed",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: "|".join(row.get(field, []))
                    if isinstance(row.get(field), list)
                    else row.get(field)
                    for field in fields
                }
            )


def _observations_from_row(
    row: Mapping[str, Any],
    *,
    source_id: str,
    source_path: Path | None,
    source_kind: str,
    inherited_sport: str | None = None,
    inherited_market: str | None = None,
) -> list[ProviderObservation]:
    providers = _provider_values(row)
    if _is_the_odds_api_bookmaker(row):
        providers.append(str(row.get("key")))
    sport = _first_text(row, SPORT_FIELDS) or inherited_sport
    market = _first_text(row, MARKET_FIELDS) or _first_market_key(row) or inherited_market
    return [
        ProviderObservation(
            raw_provider=provider,
            provider_id=normalize_provider_id(provider),
            source_id=source_id,
            source_path=str(source_path) if source_path else None,
            source_kind=source_kind,
            sport=sport,
            market=market,
        )
        for provider in sorted(set(provider for provider in providers if provider))
    ]


def _provider_values(row: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for field in PROVIDER_FIELDS:
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return values


def _is_the_odds_api_bookmaker(row: Mapping[str, Any]) -> bool:
    return (
        isinstance(row.get("key"), str)
        and isinstance(row.get("title"), str)
        and isinstance(row.get("markets"), list)
    )


def _first_market_key(row: Mapping[str, Any]) -> str | None:
    markets = row.get("markets")
    if not isinstance(markets, list):
        return None
    for market in markets:
        if isinstance(market, Mapping) and isinstance(market.get("key"), str):
            return str(market["key"]).strip() or None
    return None


def _provider_rows(observations: Sequence[ProviderObservation]) -> list[dict[str, Any]]:
    grouped: dict[str, list[ProviderObservation]] = defaultdict(list)
    for observation in observations:
        if observation.provider_id != "unknown":
            grouped[observation.provider_id].append(observation)
    rows = [_provider_summary_row(provider_id, rows) for provider_id, rows in grouped.items()]
    return sorted(rows, key=lambda row: (row["sort_rank"], row["provider_id"]))


def _provider_summary_row(provider_id: str, rows: Sequence[ProviderObservation]) -> dict[str, Any]:
    spec = provider_spec(provider_id)
    return {
        "provider_id": provider_id,
        "display_name": spec.display_name if spec else provider_id,
        "tier": spec.tier if spec else "unknown",
        "role": spec.role if spec else "unknown",
        "provider_kind": spec.provider_kind if spec else "unknown",
        "sports_strengths": list(spec.sports_strengths) if spec else [],
        "observation_count": len(rows),
        "source_kinds": sorted({row.source_kind for row in rows}),
        "source_ids": sorted({row.source_id for row in rows}),
        "sports": sorted({row.sport for row in rows if row.sport}),
        "markets": sorted({row.market for row in rows if row.market}),
        "raw_provider_examples": sorted({row.raw_provider for row in rows})[:8],
        "notes": spec.notes if spec else "Unclassified provider; cannot anchor consensus.",
        "consensus_anchor_allowed": bool(spec and spec.role in ANCHOR_ROLES),
        "requires_liquidity_caveat": bool(spec and spec.provider_kind == "exchange"),
        "requires_commission_caveat": bool(spec and spec.provider_kind == "exchange"),
        "sort_rank": _sort_rank(spec),
    }


def _coverage_gaps(
    provider_rows: Sequence[Mapping[str, Any]],
    strict_ids: set[str],
    donor_ids: set[str],
    raw_ids: set[str],
    *,
    sport_rows: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if not provider_rows:
        gaps.append(
            {
                "reason": "no_provider_sources_observed",
                "detail": "No local provider observations were found to audit.",
            }
        )
        return gaps
    if not any(is_anchor_provider(provider_id) for provider_id in strict_ids):
        gaps.append(
            {
                "reason": "strict_consensus_missing_anchor_provider",
                "detail": (
                    "The predmarket strict consensus feed does not currently include "
                    "Pinnacle, Circa, Bookmaker/BetCRIS, Asian sharps, or liquid exchange anchors."
                ),
            }
        )
    if any(is_anchor_provider(provider_id) for provider_id in donor_ids - strict_ids):
        gaps.append(
            {
                "reason": "sharp_donor_provider_not_adapted",
                "detail": (
                    "A donor artifact contains sharp or exchange providers that are not yet "
                    "wrapped into the predmarket strict consensus schema."
                ),
            }
        )
    if not any(_is_asian_sharp(provider_id) for provider_id in strict_ids | donor_ids | raw_ids):
        gaps.append(
            {
                "reason": "soccer_asian_sharp_not_observed",
                "detail": "No SBOBet/Singbet/IBC-style soccer sharp provider was observed locally.",
            }
        )
    for row in sport_rows:
        status = str(row.get("coverage_status") or "")
        sport = str(row.get("sport") or "")
        if status == "covered" or status in NON_ACTIONABLE_COVERAGE_STATUSES:
            continue
        gaps.append(
            {
                "reason": f"{sport}_strict_consensus_not_mature",
                "sport": sport,
                "detail": (
                    f"{sport} strict consensus status is {status}; strict providers="
                    f"{row.get('strict_providers')}, strict anchors={row.get('strict_anchor_providers')}."
                ),
            }
        )
    return gaps


def _recommendations(gaps: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    reasons = {str(gap.get("reason")) for gap in gaps}
    out: list[dict[str, str]] = []
    sport_gap_reasons = sorted(
        reason for reason in reasons if reason.endswith("_strict_consensus_not_mature")
    )
    if sport_gap_reasons:
        sport_gap_names = sorted(
            {
                str(gap.get("sport"))
                for gap in gaps
                if str(gap.get("reason", "")).endswith("_strict_consensus_not_mature")
                and gap.get("sport")
            }
        )
        sport_text = ", ".join(sport_gap_names) if sport_gap_names else "target sports"
        out.append(
            {
                "priority": "P0",
                "action": (
                    "Upgrade strict consensus provider coverage for active actionable gaps: "
                    f"{sport_text}. Do not let coverage in one sport mask another active gap."
                ),
            }
        )
    if "sharp_donor_provider_not_adapted" in reasons:
        out.append(
            {
                "priority": "P0",
                "action": (
                    "Wrap ATP/tennis donor exchange rows into the strict predmarket consensus "
                    "manifest before adding new models."
                ),
            }
        )
    if "strict_consensus_missing_anchor_provider" in reasons:
        out.append(
            {
                "priority": "P0",
                "action": (
                    "Upgrade the production consensus feed from secondary-only books to "
                    "Pinnacle/Circa/Bookmaker/BetCRIS or liquid exchange anchors where accessible."
                ),
            }
        )
    if "soccer_asian_sharp_not_observed" in reasons:
        out.append(
            {
                "priority": "P1",
                "action": (
                    "Source a legal timestamped soccer sharp feed with Asian handicap-aware "
                    "providers before treating World Cup consensus as mature."
                ),
            }
        )
    return out


def _summary(
    provider_rows: Sequence[Mapping[str, Any]],
    strict_ids: set[str],
    donor_ids: set[str],
    raw_ids: set[str],
    *,
    sport_rows: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    role_counts = Counter(str(row.get("role")) for row in provider_rows)
    covered_sports = [
        str(row.get("sport")) for row in sport_rows if row.get("coverage_status") == "covered"
    ]
    deferred_sports = [
        str(row.get("sport"))
        for row in sport_rows
        if row.get("coverage_status") in NON_ACTIONABLE_COVERAGE_STATUSES
    ]
    actionable_gap_sports = [
        str(row.get("sport"))
        for row in sport_rows
        if row.get("coverage_status") != "covered"
        and row.get("coverage_status") not in NON_ACTIONABLE_COVERAGE_STATUSES
    ]
    strict_consensus_sports = [
        str(row.get("sport"))
        for row in sport_rows
        if int(row.get("strict_provider_count") or 0) > 0
    ]
    return {
        "provider_count": len(provider_rows),
        "strict_consensus_provider_count": len(strict_ids),
        "donor_provider_count": len(donor_ids),
        "raw_provider_count": len(raw_ids),
        "strict_anchor_provider_count": sum(
            1 for provider_id in strict_ids if is_anchor_provider(provider_id)
        ),
        "donor_anchor_provider_count": sum(
            1 for provider_id in donor_ids if is_anchor_provider(provider_id)
        ),
        "raw_anchor_provider_count": sum(
            1 for provider_id in raw_ids if is_anchor_provider(provider_id)
        ),
        "role_counts": dict(sorted(role_counts.items())),
        "sport_target_count": len(sport_rows),
        "sport_covered_count": len(covered_sports),
        "sport_deferred_count": len(deferred_sports),
        "sport_gap_count": len(actionable_gap_sports),
        "covered_sports": covered_sports,
        "deferred_sports": deferred_sports,
        "actionable_gap_sports": actionable_gap_sports,
        "strict_consensus_sport_count": len(strict_consensus_sports),
        "strict_consensus_sports": strict_consensus_sports,
    }


def _status(
    provider_rows: Sequence[Mapping[str, Any]],
    strict_ids: set[str],
    donor_ids: set[str],
    raw_ids: set[str],
    *,
    sport_rows: Sequence[Mapping[str, Any]] = (),
) -> str:
    if not provider_rows:
        return "sports_consensus_provider_audit_blocked_no_provider_sources"
    if sport_rows and any(
        row.get("coverage_status") != "covered"
        and row.get("coverage_status") not in NON_ACTIONABLE_COVERAGE_STATUSES
        for row in sport_rows
    ):
        return "sports_consensus_provider_audit_ready_with_per_sport_gaps"
    if sport_rows and any(
        row.get("coverage_status") in NON_ACTIONABLE_COVERAGE_STATUSES for row in sport_rows
    ):
        return "sports_consensus_provider_audit_ready_with_deferred_target_sports"
    if sport_rows:
        return "sports_consensus_provider_audit_ready_all_target_sports_anchor_covered"
    if any(is_anchor_provider(provider_id) for provider_id in strict_ids):
        return "sports_consensus_provider_audit_ready_strict_anchor_present"
    if any(is_anchor_provider(provider_id) for provider_id in donor_ids - strict_ids):
        return "sports_consensus_provider_audit_ready_with_sharp_donor_gap"
    if strict_ids:
        return "sports_consensus_provider_audit_ready_strict_feed_secondary_only"
    if any(is_anchor_provider(provider_id) for provider_id in raw_ids):
        return "sports_consensus_provider_audit_ready_raw_anchor_not_wrapped"
    return "sports_consensus_provider_audit_ready_no_anchor_provider_observed"


def _source_observations(sources: Sequence[Mapping[str, Any]]) -> list[ProviderObservation]:
    observations: list[ProviderObservation] = []
    for source in sources:
        payload = source.get("payload")
        source_path = source.get("source_path")
        path = Path(source_path) if isinstance(source_path, str) and source_path else None
        observations.extend(
            collect_provider_observations(
                payload,
                source_id=str(source.get("source_id") or source_path or "local_artifact"),
                source_path=path,
                source_kind=str(source.get("source_kind") or "local_artifact"),
            )
        )
    return observations


def _sport_coverage_rows(
    observations: Sequence[ProviderObservation],
    *,
    target_sports: Sequence[str] | None,
    deferred_sports: Sequence[str] | None = None,
    incompatible_market_sports: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    target = [_canonical_sport(sport) for sport in target_sports or () if _canonical_sport(sport)]
    deferred = {
        sport for sport in (_canonical_sport(value) for value in deferred_sports or ()) if sport
    }
    incompatible = {
        sport
        for sport in (_canonical_sport(value) for value in incompatible_market_sports or ())
        if sport
    }
    if not target:
        target = sorted(
            {
                sport
                for sport in (_canonical_sport(observation.sport) for observation in observations)
                if sport
            }
        )
    rows = [
        _sport_coverage_row(
            sport,
            observations,
            deferred_sports=deferred,
            incompatible_market_sports=incompatible,
        )
        for sport in dict.fromkeys(target)
    ]
    return sorted(rows, key=lambda row: _sport_sort_rank(str(row.get("sport"))))


def _sport_coverage_row(
    sport: str,
    observations: Sequence[ProviderObservation],
    *,
    deferred_sports: set[str] | frozenset[str] = frozenset(),
    incompatible_market_sports: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any]:
    sport_observations = [
        observation
        for observation in observations
        if _canonical_sport(observation.sport) == sport and observation.provider_id != "unknown"
    ]
    strict_ids = _ids_for_sport_source_kind(sport_observations, "strict_consensus")
    donor_ids = _ids_for_sport_source_kind(sport_observations, "donor_consensus")
    raw_ids = _ids_for_sport_source_kind(sport_observations, "raw_provider_capture")
    strict_anchor_ids = {
        provider_id for provider_id in strict_ids if _provider_can_anchor_sport(provider_id, sport)
    }
    donor_anchor_ids = {
        provider_id for provider_id in donor_ids if _provider_can_anchor_sport(provider_id, sport)
    }
    raw_anchor_ids = {
        provider_id for provider_id in raw_ids if _provider_can_anchor_sport(provider_id, sport)
    }
    status = _sport_coverage_status(
        sport=sport,
        has_observations=bool(sport_observations),
        strict_ids=strict_ids,
        strict_anchor_ids=strict_anchor_ids,
        donor_anchor_ids=donor_anchor_ids,
        raw_anchor_ids=raw_anchor_ids,
        deferred_sports=set(deferred_sports),
        incompatible_market_sports=set(incompatible_market_sports),
    )
    return {
        "sport": sport,
        "coverage_status": status,
        "observation_count": len(sport_observations),
        "strict_provider_count": len(strict_ids),
        "strict_anchor_provider_count": len(strict_anchor_ids),
        "donor_anchor_provider_count": len(donor_anchor_ids),
        "raw_anchor_provider_count": len(raw_anchor_ids),
        "strict_providers": sorted(strict_ids),
        "strict_anchor_providers": sorted(strict_anchor_ids),
        "donor_anchor_providers": sorted(donor_anchor_ids),
        "raw_anchor_providers": sorted(raw_anchor_ids),
        "soccer_asian_sharp_observed": bool(
            sport != "soccer"
            or any(
                provider_id in SOCCER_ASIAN_SHARP_PROVIDERS
                for provider_id in strict_ids | donor_ids | raw_ids
            )
        ),
    }


def _sport_coverage_status(
    *,
    sport: str,
    has_observations: bool,
    strict_ids: set[str],
    strict_anchor_ids: set[str],
    donor_anchor_ids: set[str],
    raw_anchor_ids: set[str],
    deferred_sports: set[str] | frozenset[str] = frozenset(),
    incompatible_market_sports: set[str] | frozenset[str] = frozenset(),
) -> str:
    if sport in incompatible_market_sports:
        return "deferred_no_compatible_current_market"
    if sport in deferred_sports and not has_observations:
        return "deferred_no_current_rows"
    if sport == "soccer" and not any(
        provider_id in SOCCER_ASIAN_SHARP_PROVIDERS
        for provider_id in strict_ids | donor_anchor_ids | raw_anchor_ids
    ):
        return "missing_asian_sharp_reference"
    if len(strict_ids) >= 2 and strict_anchor_ids:
        return "covered"
    if strict_ids and not strict_anchor_ids:
        return "secondary_only"
    if donor_anchor_ids - strict_anchor_ids:
        return "sharp_donor_not_adapted"
    if raw_anchor_ids - strict_anchor_ids:
        return "raw_anchor_not_wrapped"
    return "missing_strict_consensus"


def _provider_can_anchor_sport(provider_id: str, sport: str) -> bool:
    spec = provider_spec(provider_id)
    if spec is None or spec.role not in ANCHOR_ROLES:
        return False
    strengths = set(spec.sports_strengths)
    return sport in strengths or (sport == "mlb" and "baseball_mlb" in strengths)


def _ids_for_sport_source_kind(
    observations: Sequence[ProviderObservation],
    source_kind: str,
) -> set[str]:
    return {
        observation.provider_id
        for observation in observations
        if observation.source_kind == source_kind and observation.provider_id != "unknown"
    }


def _source_rows(sources: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in sources:
        source_path = source.get("source_path")
        path = Path(source_path) if isinstance(source_path, str) and source_path else None
        rows.append(
            {
                "source_id": source.get("source_id"),
                "source_path": source_path,
                "source_kind": source.get("source_kind"),
                "sha256": _sha256(path) if path and path.is_file() else None,
            }
        )
    return rows


def _ids_for_source_kind(
    observations: Sequence[ProviderObservation],
    source_kind: str,
) -> set[str]:
    return {
        observation.provider_id
        for observation in observations
        if observation.source_kind == source_kind and observation.provider_id != "unknown"
    }


def _is_asian_sharp(provider_id: str) -> bool:
    return normalize_provider_id(provider_id) in {"sbobet", "singbet", "ibc"}


def _canonical_sport(value: Any) -> str | None:
    text = _normalize_alias(value)
    if not text:
        return None
    compact = text.replace(" ", "_")
    aliases = {
        "baseball_mlb": "mlb",
        "mlb": "mlb",
        "baseball": "mlb",
        "tennis_atp": "tennis",
        "tennis_wta": "tennis",
        "tennis": "tennis",
        "tennis_atp_wimbledon": "tennis",
        "soccer": "soccer",
        "football_soccer": "soccer",
        "world_cup": "soccer",
        "world_cup_soccer": "soccer",
        "fifa": "soccer",
        "fifa_world_cup": "soccer",
        "soccer_fifa_world_cup": "soccer",
        "americanfootball_nfl": "nfl",
        "football_nfl": "nfl",
        "nfl": "nfl",
        "basketball_nba": "nba",
        "nba": "nba",
        "basketball": "nba",
        "icehockey_nhl": "nhl",
        "nhl": "nhl",
        "hockey": "nhl",
    }
    return aliases.get(compact, compact)


def _sport_sort_rank(sport: str) -> tuple[int, str]:
    ranks = {sport: index for index, sport in enumerate(DEFAULT_PROVIDER_AUDIT_TARGET_SPORTS)}
    return (ranks.get(sport, 99), sport)


def _walk_dicts_with_context(
    payload: Any,
    *,
    sport: str | None = None,
    market: str | None = None,
) -> Iterable[tuple[Mapping[str, Any], str | None, str | None]]:
    if isinstance(payload, Mapping):
        row_sport = _first_text(payload, SPORT_FIELDS) or sport
        row_market = _first_text(payload, MARKET_FIELDS) or market
        if isinstance(payload.get("key"), str) and isinstance(payload.get("outcomes"), list):
            row_market = str(payload["key"]).strip() or row_market
        yield payload, row_sport, row_market
        for value in payload.values():
            yield from _walk_dicts_with_context(value, sport=row_sport, market=row_market)
    elif isinstance(payload, list):
        for value in payload:
            yield from _walk_dicts_with_context(value, sport=sport, market=market)


def _first_text(row: Mapping[str, Any], fields: Sequence[str]) -> str | None:
    for field in fields:
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _sort_rank(spec: ProviderSpec | None) -> int:
    if spec is None:
        return 90
    return {
        "A+": 0,
        "A": 10,
        "A-exchange": 15,
        "B": 30,
        "C": 50,
    }.get(spec.tier, 80)


def _stable_run_id(sources: Sequence[Mapping[str, Any]]) -> str:
    payload = [
        {
            "source_id": source.get("source_id"),
            "source_kind": source.get("source_kind"),
            "source_path": source.get("source_path"),
        }
        for source in sources
    ]
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"sports-consensus-provider-audit-{digest[:12]}"


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
