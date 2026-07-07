#!/usr/bin/env python3
"""Scout local Kalshi contract evidence for EV ledger mapping work.

This script reads local JSON files only. It does not call Kalshi, providers,
databases, account/order paths, or execution paths. The goal is to answer a
small but important question before a worker fills overlays: do we already have
local evidence for an exact Kalshi contract, official terms, and executable
cost basis that can map a model row to the EV ledger?
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from predmarket.shared_helpers import manual_drop_path

CONTROL_REPO = Path(__file__).resolve().parents[1]
MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-ev-local-contract-evidence-scout-latest"
DEFAULT_WORK_ORDER_PATH = MACRO_DIR / "latest-kalshi-ev-contract-mapping-work-order.json"
DEFAULT_SEARCH_PATHS = (
    manual_drop_path("kalshi"),
    manual_drop_path("kalshi_ev_contract_mappings"),
    CONTROL_REPO / "data",
)

JSON_SKIP_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}

NFL_ALIASES: dict[str, tuple[str, ...]] = {
    "ARI": ("ari", "arizona", "cardinals"),
    "ATL": ("atl", "atlanta", "falcons"),
    "BAL": ("bal", "baltimore", "ravens"),
    "BUF": ("buf", "buffalo", "bills"),
    "CAR": ("car", "carolina", "panthers"),
    "CHI": ("chi", "chicago", "bears"),
    "CIN": ("cin", "cincinnati", "bengals"),
    "CLE": ("cle", "cleveland", "browns"),
    "DAL": ("dal", "dallas", "cowboys"),
    "DEN": ("den", "denver", "broncos"),
    "DET": ("det", "detroit", "lions"),
    "GB": ("gb", "green bay", "packers"),
    "HOU": ("hou", "houston", "texans"),
    "IND": ("ind", "indianapolis", "colts"),
    "JAX": ("jax", "jacksonville", "jaguars"),
    "KC": ("kc", "kansas city", "chiefs"),
    "LA": ("los angeles", "rams"),
    "LAC": ("lac", "los angeles", "chargers"),
    "LAR": ("lar", "los angeles", "rams"),
    "LV": ("lv", "las vegas", "raiders"),
    "MIA": ("mia", "miami", "dolphins"),
    "MIN": ("min", "minnesota", "vikings"),
    "NE": ("ne", "new england", "patriots"),
    "NO": ("new orleans", "saints"),
    "NYG": ("nyg", "new york giants", "giants"),
    "NYJ": ("nyj", "new york jets", "jets"),
    "PHI": ("phi", "philadelphia", "eagles"),
    "PIT": ("pit", "pittsburgh", "steelers"),
    "SEA": ("sea", "seattle", "seahawks"),
    "SF": ("sf", "san francisco", "49ers", "niners"),
    "TB": ("tb", "tampa bay", "buccaneers", "bucs"),
    "TEN": ("ten", "tennessee", "titans"),
    "WAS": ("was", "washington", "commanders"),
}

TICKER_KEYS = ("contract_ticker", "ticker", "market_ticker")
EVENT_TICKER_KEYS = ("event_ticker", "event")
TITLE_KEYS = ("title", "subtitle", "sub_title", "yes_sub_title", "no_sub_title", "name")
TERMS_KEYS = (
    "rules_primary",
    "rules_secondary",
    "settlement_sources",
    "settlement_rules",
    "resolution_rule",
    "contract_terms",
)
EXECUTABLE_COST_KEYS = (
    "yes_ask_dollars",
    "yes_ask",
    "ask",
    "ask_dollars",
    "executable_price",
    "all_in_cost",
    "ticket_cost",
    "order_ticket_cost",
    "kalshi_payout_multiple",
    "ticket_payout_multiple",
    "displayed_payout_multiple",
    "payout_multiple",
)
CLEAN_TIMING_STATUSES = {"clean", "pregame_clean", "not_applicable"}
TIMING_KEYS = ("timing_status", "capture_timing_status", "source_timing_status")
CAPTURE_TIME_KEYS = ("created_at_utc", "captured_at_utc", "as_of_utc", "capture_time_utc")
FUTURE_EXPIRATION_KEYS = ("expected_expiration_time", "expiration_time", "latest_expiration_time", "close_time")
OPEN_STATUSES = {"active", "open"}
PREGAME_BUFFER = timedelta(hours=6)
TEAM_SUFFIX_ALIASES: dict[str, tuple[str, ...]] = {
    "JAX": ("JAX", "JAC"),
    "LA": ("LA", "LAR"),
    "LAR": ("LAR", "LA"),
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_local_contract_evidence_scout(
    *,
    work_order_path: Path = DEFAULT_WORK_ORDER_PATH,
    search_paths: Sequence[Path] = DEFAULT_SEARCH_PATHS,
    generated_utc: str | None = None,
    sample_limit: int = 50,
) -> dict[str, Any]:
    json_files = discover_json_files(search_paths)
    work_order = read_json_or_empty(work_order_path)
    target_rows = work_order.get("rows") if isinstance(work_order.get("rows"), list) else []
    target_rows = [row for row in target_rows if isinstance(row, Mapping)]
    files: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    parse_errors: list[dict[str, str]] = []

    for path in json_files:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parse_errors.append({"path": str(path), "error": str(exc)})
            continue
        before = len(evidence_rows)
        evidence_rows.extend(extract_contract_evidence(raw, source_path=path))
        files.append(
            {
                "path": str(path),
                "sha256": sha256_file(path),
                "contract_evidence_row_count": len(evidence_rows) - before,
            }
        )

    sport_counts: dict[str, int] = {}
    for row in evidence_rows:
        sport = str(row.get("sport") or "unknown")
        sport_counts[sport] = sport_counts.get(sport, 0) + 1

    target_matches = target_contract_matches(evidence_rows, target_rows)
    ready_matches = [
        match
        for match in target_matches
        if match.get("match_quality") == "ready_exact_local_evidence"
    ]
    possible_matches = [
        match
        for match in target_matches
        if match.get("match_quality") in {"ready_exact_local_evidence", "possible_text_match"}
    ]
    gates = local_contract_evidence_gates(
        json_file_count=len(json_files),
        contract_evidence_count=len(evidence_rows),
        target_count=len(target_rows),
        nfl_contract_evidence_count=sport_counts.get("nfl", 0),
        possible_target_match_count=len(possible_matches),
        ready_target_match_count=len(ready_matches),
    )
    if ready_matches:
        status = "local_contract_evidence_ready_for_overlay_fill"
    elif target_rows and sport_counts.get("nfl", 0):
        status = "local_contract_evidence_blocked_no_ready_target_match"
    elif target_rows:
        status = "local_contract_evidence_blocked_no_nfl_target_snapshot"
    elif evidence_rows:
        status = "local_contract_evidence_observed_no_target_work_order"
    else:
        status = "local_contract_evidence_blocked_no_contract_snapshots"

    return {
        "schema_version": 1,
        "generated_utc": generated_utc or utc_now(),
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "live_calls_made": False,
        "provider_api_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "raw_payloads_copied_to_repo": False,
        "safety": {
            "research_only": True,
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "raw_payloads_copied_to_repo": False,
        },
        "target_work_order": {
            "path": str(work_order_path),
            "present": work_order_path.is_file(),
            "sha256": sha256_file(work_order_path),
            "status": work_order.get("status"),
            "selected_contract_side_count": len(target_rows),
        },
        "search_paths": [str(path) for path in search_paths],
        "summary": {
            "json_file_count": len(json_files),
            "parsed_json_file_count": len(files),
            "parse_error_count": len(parse_errors),
            "contract_evidence_row_count": len(evidence_rows),
            "official_terms_row_count": sum(1 for row in evidence_rows if row.get("official_terms_present")),
            "executable_cost_row_count": sum(1 for row in evidence_rows if row.get("executable_cost_present")),
            "clean_timing_row_count": sum(1 for row in evidence_rows if row.get("clean_timing_present")),
            "nfl_contract_evidence_row_count": sport_counts.get("nfl", 0),
            "target_contract_side_count": len(target_rows),
            "possible_target_match_count": len(possible_matches),
            "ready_target_match_count": len(ready_matches),
            "sport_counts": dict(sorted(sport_counts.items())),
        },
        "gates": gates,
        "files": files,
        "parse_errors": parse_errors[:20],
        "contract_evidence_samples": evidence_rows[:sample_limit],
        "target_matches": target_matches,
        "next_action": local_contract_evidence_next_action(
            target_count=len(target_rows),
            ready_target_match_count=len(ready_matches),
            possible_target_match_count=len(possible_matches),
            nfl_contract_evidence_count=sport_counts.get("nfl", 0),
        ),
    }


def discover_json_files(paths: Sequence[Path]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        expanded = path.expanduser()
        if expanded.is_file() and expanded.suffix.lower() == ".json":
            candidates = [expanded]
        elif expanded.is_dir():
            candidates = [
                candidate
                for candidate in expanded.rglob("*.json")
                if not JSON_SKIP_PARTS.intersection(candidate.parts)
            ]
        else:
            candidates = []
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved not in seen:
                files.append(candidate)
                seen.add(resolved)
    return sorted(files, key=lambda item: str(item))


def extract_contract_evidence(raw: Any, *, source_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    source_capture_time = (
        first_text(raw, CAPTURE_TIME_KEYS)
        if isinstance(raw, Mapping)
        else None
    )
    for index, item in enumerate(walk_dicts(raw)):
        ticker = first_text(item, TICKER_KEYS)
        if not ticker:
            continue
        text = searchable_text(item)
        terms_fields = [key for key in TERMS_KEYS if text_value(item.get(key))]
        cost_fields = [key for key in EXECUTABLE_COST_KEYS if optional_float(item.get(key)) is not None]
        yes_bid = first_float(item, ("yes_bid_dollars", "yes_bid", "bid", "bid_dollars"))
        yes_ask = first_float(item, ("yes_ask_dollars", "yes_ask", "ask", "ask_dollars", "executable_price"))
        explicit_timing_status = first_text(item, TIMING_KEYS)
        derived_timing = derive_timing_status(item, source_capture_time=source_capture_time)
        timing_status = explicit_timing_status or derived_timing.get("timing_status")
        row = {
            "contract_ticker": ticker,
            "event_ticker": first_text(item, EVENT_TICKER_KEYS) or event_from_contract(ticker),
            "title": first_text(item, TITLE_KEYS),
            "yes_sub_title": text_value(item.get("yes_sub_title")),
            "no_sub_title": text_value(item.get("no_sub_title")),
            "sport": classify_sport(text),
            "official_terms_present": bool(terms_fields),
            "official_terms_fields": terms_fields,
            "resolution_rule": resolution_rule_text(item, terms_fields),
            "executable_cost_present": bool(cost_fields),
            "executable_cost_fields": cost_fields,
            "timing_status": timing_status,
            "timing_status_source": "explicit" if explicit_timing_status else derived_timing.get("timing_status_source"),
            "timing_reference_time": derived_timing.get("timing_reference_time"),
            "source_capture_time": source_capture_time,
            "clean_timing_present": timing_status in CLEAN_TIMING_STATUSES,
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "yes_spread": round(yes_ask - yes_bid, 6) if yes_bid is not None and yes_ask is not None else None,
            "status": text_value(item.get("status")),
            "source_path": str(source_path),
            "source_sha256": sha256_file(source_path),
            "source_object_index": index,
        }
        rows.append(row)
    rows.sort(key=lambda row: (str(row.get("sport")), str(row.get("contract_ticker"))))
    return rows


def target_contract_matches(
    evidence_rows: Sequence[Mapping[str, Any]],
    target_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for target_index, target in enumerate(target_rows):
        selection = str(target.get("selection") or "")
        opponent = str(target.get("opponent") or "")
        game = str(target.get("game") or "")
        best_score = 0
        for evidence in evidence_rows:
            if evidence.get("sport") != "nfl":
                continue
            score = target_match_score(evidence, selection=selection, opponent=opponent, game=game)
            best_score = max(best_score, score)
            if score < 4:
                continue
            ready = (
                bool(evidence.get("official_terms_present"))
                and bool(evidence.get("executable_cost_present"))
                and bool(evidence.get("clean_timing_present"))
            )
            matches.append(
                {
                    "target_index": target_index,
                    "game": game,
                    "selection": selection,
                    "opponent": opponent,
                    "contract_ticker": evidence.get("contract_ticker"),
                    "event_ticker": evidence.get("event_ticker"),
                    "source_path": evidence.get("source_path"),
                    "source_sha256": evidence.get("source_sha256"),
                    "match_score": score,
                    "match_quality": "ready_exact_local_evidence" if ready else "possible_text_match",
                    "official_terms_present": evidence.get("official_terms_present"),
                    "resolution_rule": evidence.get("resolution_rule"),
                    "executable_cost_present": evidence.get("executable_cost_present"),
                    "timing_status": evidence.get("timing_status"),
                    "clean_timing_present": evidence.get("clean_timing_present"),
                    "yes_ask": evidence.get("yes_ask"),
                    "yes_bid": evidence.get("yes_bid"),
                    "yes_spread": evidence.get("yes_spread"),
                }
            )
        if best_score == 0:
            continue
    matches.sort(
        key=lambda item: (
            item.get("match_quality") != "ready_exact_local_evidence",
            -int(item.get("match_score") or 0),
            str(item.get("game") or ""),
            str(item.get("selection") or ""),
        )
    )
    return matches


def target_match_score(evidence: Mapping[str, Any], *, selection: str, opponent: str, game: str) -> int:
    if not contract_side_matches_selection(evidence, selection):
        return 0
    text = " ".join(
        str(evidence.get(key) or "")
        for key in ("contract_ticker", "event_ticker", "title", "resolution_rule")
    ).lower()
    score = 4
    if contains_alias(text, opponent):
        score += 2
    for part in re.split(r"[@/\\s]+", game):
        if part and contains_alias(text, part):
            score += 1
    return score


def contract_side_matches_selection(evidence: Mapping[str, Any], selection: str) -> bool:
    selection = str(selection or "").upper().strip()
    if not selection:
        return False
    suffix = str(evidence.get("contract_ticker") or "").rsplit("-", 1)[-1].upper()
    if suffix and suffix in team_suffixes(selection):
        return True
    positive_text = str(evidence.get("yes_sub_title") or "").lower()
    return contains_alias(positive_text, selection)


def team_suffixes(team: str) -> tuple[str, ...]:
    team = team.upper().strip()
    return (team, *TEAM_SUFFIX_ALIASES.get(team, ()))


def contains_alias(text: str, team: str) -> bool:
    aliases = NFL_ALIASES.get(team.upper(), (team.lower(),))
    for alias in aliases:
        if not alias:
            continue
        if " " in alias:
            if alias in text:
                return True
        elif re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text):
            return True
    return False


def derive_timing_status(item: Mapping[str, Any], *, source_capture_time: str | None) -> dict[str, str | None]:
    captured_at = parse_utc_datetime(first_text(item, CAPTURE_TIME_KEYS) or source_capture_time)
    if captured_at is None:
        return {}
    status = (text_value(item.get("status")) or "").lower()
    if status and status not in OPEN_STATUSES:
        return {}
    for key in FUTURE_EXPIRATION_KEYS:
        reference_time = parse_utc_datetime(text_value(item.get(key)))
        if reference_time is None:
            continue
        if reference_time - captured_at >= PREGAME_BUFFER:
            return {
                "timing_status": "pregame_clean",
                "timing_status_source": f"derived_from_{key}_with_6h_buffer",
                "timing_reference_time": reference_time.isoformat(timespec="seconds").replace("+00:00", "Z"),
            }
    return {}


def parse_utc_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def local_contract_evidence_gates(
    *,
    json_file_count: int,
    contract_evidence_count: int,
    target_count: int,
    nfl_contract_evidence_count: int,
    possible_target_match_count: int,
    ready_target_match_count: int,
) -> list[dict[str, Any]]:
    return [
        {
            "name": "research_only_no_live_calls",
            "status": "pass",
            "reasons": ["Scout reads local JSON files only; live/provider calls are not implemented."],
        },
        {
            "name": "local_json_files_present",
            "status": "pass" if json_file_count else "blocked",
            "reasons": [f"Found {json_file_count} local JSON file(s) in configured search paths."],
        },
        {
            "name": "contract_evidence_rows_present",
            "status": "pass" if contract_evidence_count else "blocked",
            "reasons": [f"Extracted {contract_evidence_count} local Kalshi-like contract row(s)."],
        },
        {
            "name": "target_work_order_rows_present",
            "status": "pass" if target_count else "blocked",
            "reasons": [f"Loaded {target_count} target contract side(s) from the mapping work order."],
        },
        {
            "name": "nfl_contract_snapshot_present",
            "status": "pass" if nfl_contract_evidence_count else "blocked",
            "reasons": [f"Found {nfl_contract_evidence_count} local NFL contract evidence row(s)."],
        },
        {
            "name": "possible_target_match_present",
            "status": "pass" if possible_target_match_count else "blocked",
            "reasons": [f"Found {possible_target_match_count} possible target match(es)."],
        },
        {
            "name": "ready_target_contract_evidence_present",
            "status": "pass" if ready_target_match_count else "blocked",
            "reasons": [
                (
                    f"Found {ready_target_match_count} target match(es) with ticker, terms, and executable cost."
                    if ready_target_match_count
                    else "No selected NFL target has local exact ticker, official terms, and executable cost evidence."
                )
            ],
        },
        {
            "name": "clean_timing_evidence_present",
            "status": "pass" if ready_target_match_count else "blocked",
            "reasons": [
                (
                    "At least one target match includes clean timing evidence."
                    if ready_target_match_count
                    else "No selected NFL target has clean timing evidence for overlay assembly."
                )
            ],
        },
    ]


def local_contract_evidence_next_action(
    *,
    target_count: int,
    ready_target_match_count: int,
    possible_target_match_count: int,
    nfl_contract_evidence_count: int,
) -> str:
    if ready_target_match_count:
        return (
            "Use one ready target match to fill safe contract-mapping and calibrated-probability overlays outside "
            "the repo, then run make kalshi-ev-overlay-preflight && make kalshi-ev-ledger."
        )
    if possible_target_match_count:
        return (
            "Inspect the possible NFL target matches manually; do not fill overlays until official terms and "
            "executable cost are verified from the local snapshot."
        )
    if target_count and not nfl_contract_evidence_count:
        return (
            "Drop a local Kalshi NFL contract snapshot for one selected work-order game under "
            "`PREDMARKET_MANUAL_DROPS_ROOT/kalshi/`; it must include exact ticker/event_ticker, "
            "official rules, and YES ask or ticket payout/cost evidence. Contract: "
            "docs/codex/manual-drops/kalshi-ev-nfl-contract-snapshot-contract.md."
        )
    if target_count:
        return (
            "NFL contract snapshots exist locally, but none match the selected work-order games. Add or choose a "
            "snapshot matching one selected target side."
        )
    return "Refresh make kalshi-ev-contract-mapping-work-order before scouting target contract evidence."


def write_local_contract_evidence_scout(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-ev-local-contract-evidence-scout.json"
    md_path = out_dir / "kalshi-ev-local-contract-evidence-scout.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-ev-local-contract-evidence-scout.json"
    latest_md = MACRO_DIR / "latest-kalshi-ev-local-contract-evidence-scout.md"
    latest_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi EV Local Contract Evidence Scout",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Research only: `{str(report.get('research_only')).lower()}`",
        f"- Local JSON files: `{summary.get('json_file_count')}`",
        f"- Contract evidence rows: `{summary.get('contract_evidence_row_count')}`",
        f"- NFL contract evidence rows: `{summary.get('nfl_contract_evidence_row_count')}`",
        f"- Target contract sides: `{summary.get('target_contract_side_count')}`",
        f"- Possible target matches: `{summary.get('possible_target_match_count')}`",
        f"- Ready target matches: `{summary.get('ready_target_match_count')}`",
        "",
        "## Gates",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for gate in report.get("gates", []):
        reasons = "; ".join(gate.get("reasons") or [])
        lines.append(f"| `{gate.get('name')}` | `{gate.get('status')}` | {reasons} |")
    matches = report.get("target_matches") if isinstance(report.get("target_matches"), list) else []
    if matches:
        lines.extend(
            [
                "",
                "## Target Matches",
                "",
                "| Game | Selection | Contract | Quality | Ask | Source |",
                "| --- | --- | --- | --- | ---: | --- |",
            ]
        )
        for match in matches[:20]:
            lines.append(
                f"| `{match.get('game')}` | `{match.get('selection')}` | `{match.get('contract_ticker')}` | "
                f"`{match.get('match_quality')}` | {match.get('yes_ask')} | `{match.get('source_path')}` |"
            )
    lines.extend(["", "## Next Action", "", str(report.get("next_action") or ""), ""])
    return "\n".join(lines)


def walk_dicts(value: Any):
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def searchable_text(item: Mapping[str, Any]) -> str:
    pieces: list[str] = []
    for key in (*TICKER_KEYS, *EVENT_TICKER_KEYS, *TITLE_KEYS, *TERMS_KEYS):
        value = text_value(item.get(key))
        if value:
            pieces.append(value)
    return " ".join(pieces).lower()


def classify_sport(text: str) -> str:
    if any(token in text for token in ("xmlb", "mlb", "baseball")):
        return "mlb"
    if any(token in text for token in ("cfl", "canadian football")):
        return "cfl"
    if "kxnfl" in text or re.search(r"(?<![a-z0-9])nfl(?![a-z0-9])", text) or "super bowl" in text:
        return "nfl"
    if any(token in text for token in ("nba", "basketball")):
        return "nba"
    if any(token in text for token in ("atp", "tennis", "wimbledon")):
        return "atp"
    return "unknown"


def first_text(item: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = text_value(item.get(key))
        if value:
            return value
    return None


def first_float(item: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        value = optional_float(item.get(key))
        if value is not None:
            return value
    return None


def resolution_rule_text(item: Mapping[str, Any], fields: Sequence[str]) -> str | None:
    parts: list[str] = []
    for key in fields:
        value = text_value(item.get(key))
        if value:
            parts.append(f"{key}: {value}")
    return "\n\n".join(parts) or None


def text_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts = [text_value(item) for item in value]
        joined = "; ".join(part for part in parts if part)
        return joined or None
    if isinstance(value, Mapping):
        return json.dumps(value, sort_keys=True)
    return None


def optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip().rstrip("x%")
            if not value:
                return None
        return float(value)
    except (TypeError, ValueError):
        return None


def event_from_contract(contract: str) -> str | None:
    if "-" not in contract:
        return None
    return "-".join(contract.split("-")[:-1]) or None


def read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    raw = digest.hexdigest()
    return "sha256:" + " ".join(raw[index : index + 8] for index in range(0, len(raw), 8))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-order-path", type=Path, default=DEFAULT_WORK_ORDER_PATH)
    parser.add_argument("--search-path", type=Path, action="append")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--sample-limit", type=int, default=50)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_local_contract_evidence_scout(
        work_order_path=args.work_order_path,
        search_paths=args.search_path or DEFAULT_SEARCH_PATHS,
        sample_limit=args.sample_limit,
    )
    if args.write:
        paths = write_local_contract_evidence_scout(report, args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
