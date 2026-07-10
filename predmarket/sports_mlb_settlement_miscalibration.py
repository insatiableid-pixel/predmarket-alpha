"""Fixed-clock MLB moneyline settlement-miscalibration factory.

Research-only helpers that:
- reconstruct fixed pregame decision clocks from executable books;
- join exact public Kalshi settlement truth;
- keep calibration residuals separate from hold-to-settlement economics;
- evaluate a finite pre-registered hypothesis family with event-grouped
  walk-forward validation and complete-family FDR.

Does not size, stake, open accounts, or submit orders.
"""

from __future__ import annotations

# ruff: noqa: C901
import hashlib
import json
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from predmarket.kalshi_execution_cost import GENERAL_TAKER_FEE_RATE, kalshi_trade_fee
from predmarket.shared_helpers import (
    json_float,
    optional_float,
    timestamp,
)

FAMILY_ID = "sports_mlb_settlement_miscalibration_v1"
SERIES_ALLOWLIST = frozenset({"KXMLBGAME"})

# Decision clocks relative to scheduled game start (seconds before start).
DEFAULT_CLOCKS_SECONDS: dict[str, int] = {
    "T-24h": 24 * 3600,
    "T-6h": 6 * 3600,
    "T-60m": 3600,
    "T-15m": 900,
}

# Max age of the latest book at or before the clock (seconds).
# Frozen from capture-gap inventory (microstructure median inter-snapshot gap ~27m;
# p90 much larger). These ceilings are input-quality constraints, not outcome-tuned.
DEFAULT_STALENESS_SECONDS: dict[str, int] = {
    "T-24h": 6 * 3600,
    "T-6h": 2 * 3600,
    "T-60m": 45 * 60,
    "T-15m": 30 * 60,
}

# Pre-registered power gates (event-level independence unit).
MIN_DISCOVERY_EVENTS = 40
MIN_OOS_EVENTS = 20
MIN_CONFIRMATION_EVENTS = 15
FDR_ALPHA = 0.05

MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}
TICKER_START_RE = re.compile(
    r"^KXMLBGAME-(?P<yy>\d{2})(?P<mon>[A-Z]{3})(?P<dd>\d{2})(?P<hhmm>\d{4})",
    re.IGNORECASE,
)

PRIOR_NEGATIVE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "family": "sports_consensus_historical",
        "spec_id": "historical_mlb_multi_book_consensus_v1",
        "status": "falsified",
        "do_not_repeat": "Cosmetic threshold/bucket renames of the same consensus divergence specs",
    },
    {
        "family": "near_resolution_informed_flow",
        "spec_id": "near_resolution_simple_flow_forward_mid_v1",
        "status": "falsified",
        "do_not_repeat": "Same mid-direction forward labels with cosmetic momentum/imbalance renames",
    },
    {
        "family": "passive_liquidity_provision",
        "spec_id": "passive_liquidity_public_snapshot_paper_fill_v1",
        "status": "falsified",
        "do_not_repeat": "Same maker paper-fill specs on public snapshots without new fill truth",
    },
    {
        "family": "near_resolution_informed_flow",
        "spec_id": "flow_depth_imbalance_settlement_directional_v1",
        "status": "confirmation_failed",
        "do_not_repeat": "Resurrecting settlement-direction depth imbalance without new mechanism",
    },
    {
        "family": "sports_executable_horizon_microstructure_v1",
        "spec_id": "sports_executable_horizon_microstructure_v1",
        "status": "falsified",
        "do_not_repeat": "Short-horizon next-mid / executable round-trip microstructure retunes",
    },
    {
        "family": "sports_cross_contract_leadlag_v1",
        "spec_id": "sports_cross_contract_leadlag_v1",
        "status": "falsified",
        "do_not_repeat": "Cross-contract short-horizon lead-lag retunes",
    },
    {
        "family": "sports_thin_book_fade_v1",
        "spec_id": "sports_thin_book_fade_v1",
        "status": "falsified",
        "do_not_repeat": "Thin-book short-horizon fade retunes",
    },
    {
        "family": "sports_consensus_price_bucket_bias",
        "spec_id": "sports_consensus_price_bucket_bias",
        "status": "baseline_only",
        "do_not_repeat": (
            "Static favorite-longshot buckets may be retained only as baseline/negative "
            "control; cosmetic bucket renames are not novel candidates"
        ),
    },
)


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def taker_fee(price: float, *, contract_count: float = 1.0) -> float:
    return float(
        kalshi_trade_fee(
            price=price,
            contract_count=contract_count,
            fee_rate=GENERAL_TAKER_FEE_RATE,
        )
    )


def validate_book(bid: float | None, ask: float | None) -> tuple[bool, str | None]:
    if bid is None or ask is None:
        return False, "missing_bid_or_ask"
    if not (0.0 <= bid <= 1.0 and 0.0 <= ask <= 1.0):
        return False, "price_out_of_bounds"
    if bid > ask:
        return False, "crossed_book"
    return True, None


def microprice(
    bid: float | None,
    ask: float | None,
    bid_depth: float | None,
    ask_depth: float | None,
) -> float | None:
    if bid is None or ask is None:
        return None
    bd = 0.0 if bid_depth is None else max(0.0, float(bid_depth))
    ad = 0.0 if ask_depth is None else max(0.0, float(ask_depth))
    total = bd + ad
    if total <= 0:
        return (float(bid) + float(ask)) / 2.0
    return (float(ask) * bd + float(bid) * ad) / total


def settlement_outcome(market: Mapping[str, Any]) -> int | None:
    result = str(market.get("result") or market.get("settlement_result") or "").strip().lower()
    if result in {"yes", "true", "1"}:
        return 1
    if result in {"no", "false", "0"}:
        return 0
    value = optional_float(market.get("settlement_value_dollars", market.get("settlement_value")))
    if value is None:
        value = optional_float(market.get("yes_outcome"))
    if value is None:
        return None
    if value >= 0.999:
        return 1
    if value <= 0.001:
        return 0
    return None


def parse_game_start_from_ticker(ticker: str) -> float | None:
    match = TICKER_START_RE.match(str(ticker or ""))
    if not match:
        return None
    year = 2000 + int(match.group("yy"))
    month = MONTHS.get(match.group("mon").upper())
    if month is None:
        return None
    day = int(match.group("dd"))
    hhmm = match.group("hhmm")
    hour = int(hhmm[:2])
    minute = int(hhmm[2:])
    # Kalshi MLB moneyline tickers encode local-ish kickoff; occurrence_datetime is
    # preferred when present. Ticker parse is a fallback and marked as such upstream.
    try:
        from datetime import UTC, datetime

        return datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp()
    except ValueError:
        return None


def resolve_game_start(market: Mapping[str, Any], *, ticker: str) -> tuple[float | None, str]:
    for key in (
        "occurrence_datetime",
        "expected_expiration_time",
        "game_start_utc",
        "scheduled_start_utc",
    ):
        ts = timestamp(market.get(key))
        if ts is not None:
            return ts, key
    parsed = parse_game_start_from_ticker(ticker)
    if parsed is not None:
        return parsed, "ticker_embedded_kickoff_utc_fallback"
    close_ts = timestamp(market.get("close_time"))
    if close_ts is not None:
        return close_ts, "close_time_fallback"
    return None, "missing_game_start"


def derive_event_ticker(ticker: str) -> str:
    text = str(ticker or "")
    if "-" not in text:
        return text
    head, tail = text.rsplit("-", 1)
    if len(tail) <= 4 and tail.isalpha():
        return head
    return text


def series_from_ticker(ticker: str) -> str:
    text = str(ticker or "")
    return text.split("-", 1)[0] if text else ""


def load_json_rows(path: Path, list_keys: Sequence[str]) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in list_keys:
        rows = payload.get(key)
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, Mapping)]
    return []


def load_observation_packets(
    observation_dirs: Sequence[Path],
) -> list[dict[str, Any]]:
    """Load and normalize MLB moneyline book snapshots from research packets."""
    by_id: dict[str, dict[str, Any]] = {}
    for observation_dir in observation_dirs:
        if not observation_dir.is_dir():
            continue
        for path in sorted(observation_dir.glob("*.json")):
            source_hash = sha256_file(path)
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            rows = payload.get("rows") if isinstance(payload, Mapping) else payload
            if not isinstance(rows, list):
                continue
            for index, row in enumerate(rows):
                if not isinstance(row, Mapping):
                    continue
                item = normalize_observation_row(
                    row,
                    source_path=str(path),
                    source_sha256=source_hash,
                    index=index,
                )
                if item is None:
                    continue
                snapshot_id = str(item["snapshot_id"])
                if snapshot_id not in by_id:
                    by_id[snapshot_id] = item
    return sorted(
        by_id.values(),
        key=lambda row: (
            str(row.get("contract_ticker") or ""),
            float(row.get("observed_ts") or 0.0),
            str(row.get("snapshot_id") or ""),
        ),
    )


def normalize_observation_row(
    row: Mapping[str, Any],
    *,
    source_path: str,
    source_sha256: str | None,
    index: int,
) -> dict[str, Any] | None:
    ticker = str(row.get("contract_ticker") or row.get("ticker") or "").strip()
    if not ticker.startswith("KXMLBGAME"):
        return None
    observed = (
        row.get("observed_at_utc")
        or row.get("quote_time")
        or row.get("decision_time")
        or row.get("observed_utc")
        or row.get("model_time")
    )
    observed_ts = timestamp(observed)
    if observed_ts is None:
        return None

    yes_bid = optional_float(
        row.get("best_yes_bid", row.get("yes_bid", row.get("yes_bid_dollars")))
    )
    yes_ask = optional_float(
        row.get("best_yes_ask", row.get("yes_ask", row.get("yes_ask_dollars")))
    )
    no_bid = optional_float(row.get("best_no_bid", row.get("no_bid", row.get("no_bid_dollars"))))
    no_ask = optional_float(row.get("best_no_ask", row.get("no_ask", row.get("no_ask_dollars"))))
    # Independent NO book only; do not invent complementary asks when missing.
    if no_bid is None and yes_ask is not None and 0.0 <= yes_ask <= 1.0:
        # Complementary bid is recoverable from YES ask only as a diagnostic, not as NO ask.
        pass
    if no_ask is None and yes_bid is not None and 0.0 <= yes_bid <= 1.0:
        pass

    yes_bid_depth = optional_float(row.get("yes_bid_depth_top1"))
    yes_ask_depth = optional_float(row.get("yes_ask_depth_top1"))
    no_bid_depth = optional_float(row.get("no_bid_depth_top1"))
    no_ask_depth = optional_float(row.get("no_ask_depth_top1"))
    yes_mid = optional_float(row.get("yes_mid"))
    if yes_mid is None and yes_bid is not None and yes_ask is not None:
        yes_mid = (yes_bid + yes_ask) / 2.0
    spread = optional_float(row.get("yes_spread"))
    if spread is None and yes_bid is not None and yes_ask is not None:
        spread = yes_ask - yes_bid
    mp = microprice(yes_bid, yes_ask, yes_bid_depth, yes_ask_depth)
    event = str(row.get("event_ticker") or derive_event_ticker(ticker))
    series = str(row.get("series_ticker") or series_from_ticker(ticker))
    snapshot_id = str(row.get("snapshot_id") or "").strip()
    if not snapshot_id:
        snapshot_id = sha256_text(f"{ticker}|{observed}|{source_path}|{index}")[:24]
    entry_source = str(
        row.get("entry_source") or row.get("quote_source") or "orderbook_observation"
    )
    return {
        "snapshot_id": snapshot_id,
        "contract_ticker": ticker,
        "event_ticker": event,
        "series_ticker": series,
        "observed_at_utc": observed,
        "observed_ts": observed_ts,
        "best_yes_bid": json_float(yes_bid),
        "best_yes_ask": json_float(yes_ask),
        "best_no_bid": json_float(no_bid),
        "best_no_ask": json_float(no_ask),
        "yes_bid_depth_top1": json_float(yes_bid_depth),
        "yes_ask_depth_top1": json_float(yes_ask_depth),
        "no_bid_depth_top1": json_float(no_bid_depth),
        "no_ask_depth_top1": json_float(no_ask_depth),
        "yes_mid": json_float(yes_mid),
        "microprice": json_float(mp),
        "yes_spread": json_float(spread),
        "total_depth_contracts": json_float(optional_float(row.get("total_depth_contracts"))),
        "depth_imbalance_yes": json_float(optional_float(row.get("depth_imbalance_yes"))),
        "open_time": row.get("open_time"),
        "created_time": row.get("created_time"),
        "settlement_time": row.get("settlement_time") or row.get("settled_time"),
        "entry_source": entry_source,
        "raw_orderbook_sha256": row.get("raw_orderbook_sha256"),
        "_source_path": source_path,
        "_source_sha256": source_sha256,
        "usable": False,
        "research_only": True,
        "execution_enabled": False,
    }


def load_settlement_markets(paths: Sequence[Path]) -> dict[str, dict[str, Any]]:
    by_ticker: dict[str, dict[str, Any]] = {}
    for path in paths:
        if path.is_dir():
            files = sorted(path.glob("*.json"))
        elif path.is_file():
            files = [path]
        else:
            continue
        for file_path in files:
            source_hash = sha256_file(file_path)
            rows = load_json_rows(
                file_path,
                ("markets", "settled_markets", "rows", "labels", "settlements"),
            )
            for row in rows:
                ticker = str(row.get("ticker") or row.get("contract_ticker") or "").strip()
                if not ticker.startswith("KXMLBGAME"):
                    continue
                outcome = settlement_outcome(row)
                if outcome is None and optional_float(row.get("yes_outcome")) is not None:
                    outcome = int(optional_float(row.get("yes_outcome")) or 0)
                if outcome is None:
                    continue
                item = dict(row)
                item["contract_ticker"] = ticker
                item["yes_outcome"] = int(outcome)
                item["_source_path"] = str(file_path)
                item["_source_sha256"] = source_hash
                # Prefer finalized market payloads over sparse label rows when both exist.
                existing = by_ticker.get(ticker)
                if existing is None or (
                    existing.get("result") is None and item.get("result") is not None
                ):
                    by_ticker[ticker] = item
    return by_ticker


def select_asof_book(
    books: Sequence[Mapping[str, Any]],
    *,
    clock_ts: float,
    max_staleness_seconds: float,
) -> tuple[Mapping[str, Any] | None, str]:
    """Latest book at or before clock_ts within staleness; never future books."""
    candidates: list[tuple[float, Mapping[str, Any]]] = []
    for row in books:
        ts = optional_float(row.get("observed_ts"))
        if ts is None or ts > clock_ts:
            continue
        age = clock_ts - float(ts)
        if age > max_staleness_seconds:
            continue
        candidates.append((float(ts), row))
    if not candidates:
        # Distinguish missing vs stale for diagnostics.
        prior = [
            float(row["observed_ts"])
            for row in books
            if optional_float(row.get("observed_ts")) is not None
            and float(row["observed_ts"]) <= clock_ts
        ]
        if not prior:
            return None, "censored_missing_book"
        return None, "censored_stale_book"
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1], "matched"


def build_path_features(
    books: Sequence[Mapping[str, Any]],
    *,
    decision_ts: float,
    lookback_seconds: float = 5 * 3600,
) -> dict[str, float | None]:
    history = [
        row
        for row in books
        if optional_float(row.get("observed_ts")) is not None
        and decision_ts - lookback_seconds <= float(row["observed_ts"]) < decision_ts
        and optional_float(row.get("yes_mid")) is not None
    ]
    history = sorted(history, key=lambda row: float(row["observed_ts"]))
    if len(history) < 2:
        return {
            "path_mid_slope_per_hour": None,
            "path_mid_vol": None,
            "path_mid_drawdown": None,
            "path_n_points": float(len(history)),
        }
    mids = [float(row["yes_mid"]) for row in history]
    times = [float(row["observed_ts"]) for row in history]
    hours = max(1e-6, (times[-1] - times[0]) / 3600.0)
    slope = (mids[-1] - mids[0]) / hours
    peak = mids[0]
    max_dd = 0.0
    for mid in mids:
        peak = max(peak, mid)
        max_dd = max(max_dd, peak - mid)
    vol = statistics.pstdev(mids) if len(mids) >= 2 else 0.0
    return {
        "path_mid_slope_per_hour": slope,
        "path_mid_vol": vol,
        "path_mid_drawdown": max_dd,
        "path_n_points": float(len(history)),
    }


def hold_to_settlement_economics(
    *,
    side: str,
    yes_ask: float | None,
    no_ask: float | None,
    yes_outcome: int,
    yes_ask_depth: float | None,
    no_ask_depth: float | None,
) -> dict[str, Any]:
    """Enter at contemporaneous executable ask; hold to settlement; one taker fee."""
    side_norm = side.lower().strip()
    if side_norm not in {"yes", "no"}:
        return _blocked_econ("invalid_side")
    if side_norm == "yes":
        ask = yes_ask
        depth = yes_ask_depth
        payoff = float(yes_outcome)
    else:
        ask = no_ask
        depth = no_ask_depth
        payoff = 1.0 - float(yes_outcome)
    if ask is None:
        return _blocked_econ(f"missing_{side_norm}_ask")
    ask_f = float(ask)
    if not (0.0 < ask_f < 1.0):
        return _blocked_econ("ask_not_tradable")
    fee = taker_fee(ask_f)
    net = payoff - ask_f - fee
    gross = payoff - ask_f
    return {
        "label_status": "hold_to_settlement_labeled",
        "side": side_norm,
        "entry_ask": json_float(ask_f),
        "entry_fee": json_float(fee),
        "settlement_payoff": json_float(payoff),
        "gross_payoff_per_contract": json_float(gross),
        "net_payoff_per_contract": json_float(net),
        "capacity_contracts": json_float(depth),
        "blocker": None,
    }


def _blocked_econ(reason: str) -> dict[str, Any]:
    return {
        "label_status": "blocked",
        "side": None,
        "entry_ask": None,
        "entry_fee": None,
        "settlement_payoff": None,
        "gross_payoff_per_contract": None,
        "net_payoff_per_contract": None,
        "capacity_contracts": None,
        "blocker": reason,
    }


def build_fixed_clock_labels(
    observations: Sequence[Mapping[str, Any]],
    settlements: Mapping[str, Mapping[str, Any]],
    *,
    clocks: Mapping[str, int] | None = None,
    staleness: Mapping[str, int] | None = None,
    discovery_cutoff_utc: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    clock_map = dict(clocks or DEFAULT_CLOCKS_SECONDS)
    stale_map = dict(staleness or DEFAULT_STALENESS_SECONDS)
    cutoff_ts = timestamp(discovery_cutoff_utc) if discovery_cutoff_utc else None

    by_ticker: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in observations:
        ticker = str(row.get("contract_ticker") or "")
        if ticker:
            by_ticker[ticker].append(row)

    labels: list[dict[str, Any]] = []
    quality: Counter[str] = Counter()
    clock_coverage: dict[str, Counter[str]] = {name: Counter() for name in clock_map}
    events_by_clock: dict[str, set[str]] = {name: set() for name in clock_map}

    for ticker, books in by_ticker.items():
        market = settlements.get(ticker)
        if market is None:
            quality["missing_settlement"] += 1
            continue
        yes_outcome = settlement_outcome(market)
        if yes_outcome is None:
            quality["unparseable_settlement"] += 1
            continue
        game_start_ts, game_start_source = resolve_game_start(market, ticker=ticker)
        if game_start_ts is None:
            quality["missing_game_start"] += 1
            continue
        open_ts = timestamp(market.get("open_time") or market.get("created_time"))
        ordered = sorted(books, key=lambda row: float(row.get("observed_ts") or 0.0))
        event = str(
            market.get("event_ticker")
            or (ordered[0].get("event_ticker") if ordered else None)
            or derive_event_ticker(ticker)
        )

        # Precompute path features at each book time for slope joins.
        for clock_name, offset in clock_map.items():
            clock_ts = float(game_start_ts) - float(offset)
            if cutoff_ts is not None and clock_ts > cutoff_ts:
                quality["post_cutoff_excluded"] += 1
                clock_coverage[clock_name]["post_cutoff"] += 1
                continue
            book, match_status = select_asof_book(
                ordered,
                clock_ts=clock_ts,
                max_staleness_seconds=float(stale_map[clock_name]),
            )
            clock_coverage[clock_name][match_status] += 1
            if book is None:
                labels.append(
                    {
                        "label_id": f"{ticker}|{clock_name}|censored",
                        "feature_family": FAMILY_ID,
                        "contract_ticker": ticker,
                        "event_ticker": event,
                        "series_ticker": series_from_ticker(ticker),
                        "clock_name": clock_name,
                        "clock_offset_seconds": int(offset),
                        "game_start_ts": game_start_ts,
                        "game_start_source": game_start_source,
                        "decision_ts": clock_ts,
                        "label_status": match_status,
                        "yes_outcome": int(yes_outcome),
                        "usable": False,
                        "research_only": True,
                        "execution_enabled": False,
                    }
                )
                quality[match_status] += 1
                continue

            yes_bid = optional_float(book.get("best_yes_bid"))
            yes_ask = optional_float(book.get("best_yes_ask"))
            no_bid = optional_float(book.get("best_no_bid"))
            no_ask = optional_float(book.get("best_no_ask"))
            no_ask_source = "observed_no_ask"
            # Buying NO at (1 - yes_bid) is the standard Kalshi executable NO entry
            # when YES bid is a valid independent quote. Never invent NO ask from a
            # missing/invalid YES bid.
            if no_ask is None and yes_bid is not None and 0.0 < float(yes_bid) < 1.0:
                no_ask = 1.0 - float(yes_bid)
                no_ask_source = "complement_of_valid_yes_bid"
            ok_yes_two_sided, reason_yes = validate_book(yes_bid, yes_ask)
            yes_ask_ok = yes_ask is not None and 0.0 < float(yes_ask) < 1.0
            no_ask_ok = no_ask is not None and 0.0 < float(no_ask) < 1.0
            if not ok_yes_two_sided:
                quality[f"yes_two_sided_{reason_yes}"] += 1
            yes_mid = optional_float(book.get("yes_mid"))
            if yes_mid is None and yes_bid is not None and yes_ask is not None:
                yes_mid = (float(yes_bid) + float(yes_ask)) / 2.0
            mp = optional_float(book.get("microprice"))
            if mp is None:
                mp = microprice(
                    yes_bid,
                    yes_ask,
                    optional_float(book.get("yes_bid_depth_top1")),
                    optional_float(book.get("yes_ask_depth_top1")),
                )
            # Calibration estimator prefers microprice, then mid (not ask-only).
            p_hat = mp if mp is not None else yes_mid
            residual = None if p_hat is None else float(yes_outcome) - float(p_hat)
            path = build_path_features(ordered, decision_ts=float(book["observed_ts"]))
            listing_age_hours = None
            if open_ts is not None:
                listing_age_hours = max(0.0, (float(book["observed_ts"]) - open_ts) / 3600.0)
            book_age = float(clock_ts) - float(book["observed_ts"])

            yes_econ = hold_to_settlement_economics(
                side="yes",
                yes_ask=yes_ask,
                no_ask=no_ask,
                yes_outcome=int(yes_outcome),
                yes_ask_depth=optional_float(book.get("yes_ask_depth_top1")),
                no_ask_depth=optional_float(book.get("no_ask_depth_top1")),
            )
            no_econ = hold_to_settlement_economics(
                side="no",
                yes_ask=yes_ask,
                no_ask=no_ask,
                yes_outcome=int(yes_outcome),
                yes_ask_depth=optional_float(book.get("yes_ask_depth_top1")),
                no_ask_depth=optional_float(book.get("no_ask_depth_top1")),
            )

            label_status = "labeled"
            if not yes_ask_ok and not no_ask_ok:
                label_status = f"blocked_no_executable_ask_{reason_yes or 'missing'}"
            elif yes_econ["blocker"] and no_econ["blocker"]:
                label_status = "blocked_no_executable_side"
            else:
                events_by_clock[clock_name].add(event)

            quality[label_status] += 1
            brier = None if p_hat is None else (float(yes_outcome) - float(p_hat)) ** 2
            labels.append(
                {
                    "label_id": f"{ticker}|{clock_name}|{book.get('snapshot_id')}",
                    "feature_family": FAMILY_ID,
                    "snapshot_id": book.get("snapshot_id"),
                    "contract_ticker": ticker,
                    "event_ticker": event,
                    "series_ticker": series_from_ticker(ticker),
                    "clock_name": clock_name,
                    "clock_offset_seconds": int(offset),
                    "game_start_ts": game_start_ts,
                    "game_start_source": game_start_source,
                    "decision_ts": clock_ts,
                    "book_observed_at_utc": book.get("observed_at_utc"),
                    "book_observed_ts": book.get("observed_ts"),
                    "book_age_seconds": json_float(book_age),
                    "entry_source": book.get("entry_source"),
                    "source_path": book.get("_source_path"),
                    "source_sha256": book.get("_source_sha256"),
                    "raw_orderbook_sha256": book.get("raw_orderbook_sha256"),
                    "open_time": market.get("open_time") or book.get("open_time"),
                    "listing_age_hours": json_float(listing_age_hours),
                    "yes_outcome": int(yes_outcome),
                    "settlement_result": market.get("result") or market.get("settlement_result"),
                    "settlement_source_path": market.get("_source_path"),
                    "settlement_source_sha256": market.get("_source_sha256"),
                    "best_yes_bid": json_float(yes_bid),
                    "best_yes_ask": json_float(yes_ask),
                    "best_no_bid": json_float(no_bid),
                    "best_no_ask": json_float(no_ask),
                    "no_ask_source": no_ask_source,
                    "yes_mid": json_float(yes_mid),
                    "microprice": json_float(mp),
                    "p_hat": json_float(p_hat),
                    "calibration_residual": json_float(residual),
                    "brier": json_float(brier),
                    "yes_spread": json_float(optional_float(book.get("yes_spread"))),
                    "yes_ask_depth_top1": json_float(
                        optional_float(book.get("yes_ask_depth_top1"))
                    ),
                    "no_ask_depth_top1": json_float(optional_float(book.get("no_ask_depth_top1"))),
                    "total_depth_contracts": json_float(
                        optional_float(book.get("total_depth_contracts"))
                    ),
                    "path_mid_slope_per_hour": json_float(path["path_mid_slope_per_hour"]),
                    "path_mid_vol": json_float(path["path_mid_vol"]),
                    "path_mid_drawdown": json_float(path["path_mid_drawdown"]),
                    "path_n_points": json_float(path["path_n_points"]),
                    "yes_entry_ask": yes_econ["entry_ask"],
                    "yes_entry_fee": yes_econ["entry_fee"],
                    "yes_settlement_payoff": yes_econ["settlement_payoff"],
                    "yes_gross_payoff": yes_econ["gross_payoff_per_contract"],
                    "yes_net_payoff": yes_econ["net_payoff_per_contract"],
                    "yes_capacity": yes_econ["capacity_contracts"],
                    "yes_blocker": yes_econ["blocker"],
                    "no_entry_ask": no_econ["entry_ask"],
                    "no_entry_fee": no_econ["entry_fee"],
                    "no_settlement_payoff": no_econ["settlement_payoff"],
                    "no_gross_payoff": no_econ["gross_payoff_per_contract"],
                    "no_net_payoff": no_econ["net_payoff_per_contract"],
                    "no_capacity": no_econ["capacity_contracts"],
                    "no_blocker": no_econ["blocker"],
                    "label_status": label_status,
                    "usable": False,
                    "research_only": True,
                    "execution_enabled": False,
                }
            )

    # Attach clock-to-clock geometry after first pass.
    labels = attach_clock_geometry(labels)

    summary = {
        "observation_row_count": len(observations),
        "settlement_ticker_count": len(settlements),
        "label_row_count": len(labels),
        "labeled_row_count": sum(1 for row in labels if row.get("label_status") == "labeled"),
        "clocks_seconds": clock_map,
        "staleness_seconds": stale_map,
        "quality_counts": dict(quality),
        "clock_coverage": {name: dict(counter) for name, counter in clock_coverage.items()},
        "events_by_clock": {name: len(values) for name, values in events_by_clock.items()},
        "distinct_contract_count": len({row.get("contract_ticker") for row in labels}),
        "distinct_event_count": len(
            {row.get("event_ticker") for row in labels if row.get("event_ticker")}
        ),
        "discovery_cutoff_utc": discovery_cutoff_utc,
    }
    return labels, summary


def attach_clock_geometry(labels: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_contract: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in labels:
        if row.get("label_status") != "labeled":
            continue
        by_contract[str(row.get("contract_ticker"))][str(row.get("clock_name"))] = row
    output: list[dict[str, Any]] = []
    for row in labels:
        item = dict(row)
        ticker = str(item.get("contract_ticker") or "")
        clocks = by_contract.get(ticker, {})
        p_24 = optional_float((clocks.get("T-24h") or {}).get("p_hat"))
        p_6 = optional_float((clocks.get("T-6h") or {}).get("p_hat"))
        p_60 = optional_float((clocks.get("T-60m") or {}).get("p_hat"))
        p_15 = optional_float((clocks.get("T-15m") or {}).get("p_hat"))
        item["clock_delta_6h_to_60m"] = (
            None if p_6 is None or p_60 is None else json_float(p_60 - p_6)
        )
        item["clock_delta_60m_to_15m"] = (
            None if p_60 is None or p_15 is None else json_float(p_15 - p_60)
        )
        item["clock_delta_24h_to_60m"] = (
            None if p_24 is None or p_60 is None else json_float(p_60 - p_24)
        )
        item["abs_clock_delta_6h_to_60m"] = (
            None
            if item["clock_delta_6h_to_60m"] is None
            else json_float(abs(float(item["clock_delta_6h_to_60m"])))
        )
        output.append(item)
    return output


def hypothesis_registry() -> list[dict[str, Any]]:
    """Finite pre-registered family. Static buckets are baselines, not novel."""
    return [
        {
            "model_id": "baseline_static_longshot_buy_yes_t60m",
            "clock_name": "T-60m",
            "side": "yes",
            "feature": "p_hat",
            "direction": "in_range",
            "range": [0.15, 0.30],
            "negative_control": False,
            "baseline_only": True,
            "mechanism": "Static longshot buy baseline/control (not a novel claim).",
            "expected_direction": "often_negative_after_fees",
            "calibration_null": "E[Y|p]=p in bucket",
            "economic_null": "mean net payoff <= 0 after ask+fee",
        },
        {
            "model_id": "baseline_static_favorite_buy_yes_t60m",
            "clock_name": "T-60m",
            "side": "yes",
            "feature": "p_hat",
            "direction": "in_range",
            "range": [0.70, 0.90],
            "negative_control": False,
            "baseline_only": True,
            "mechanism": "Static favorite buy baseline/control.",
            "expected_direction": "near_zero_or_negative_after_fees",
            "calibration_null": "E[Y|p]=p in bucket",
            "economic_null": "mean net payoff <= 0 after ask+fee",
        },
        {
            "model_id": "clock_x_price_fade_favorite_t60m",
            "clock_name": "T-60m",
            "side": "no",
            "feature": "p_hat",
            "direction": "gt",
            "threshold": 0.72,
            "negative_control": False,
            "baseline_only": False,
            "mechanism": (
                "Fixed-clock interaction: near kickoff, high YES prices overstate win chance; "
                "buy NO at executable NO ask and hold to settlement."
            ),
            "expected_direction": "positive_calibration_residual_for_no",
            "calibration_null": "E[Y|p,T-60m]=p",
            "economic_null": "mean net payoff <= 0 after ask+fee",
        },
        {
            "model_id": "clock_x_price_buy_underdog_t6h",
            "clock_name": "T-6h",
            "side": "yes",
            "feature": "p_hat",
            "direction": "in_range",
            "range": [0.28, 0.42],
            "negative_control": False,
            "baseline_only": False,
            "mechanism": (
                "T-6h underdogs in a moderate band are underpriced relative to settlement "
                "frequency (clock x price, not static all-clock bucket)."
            ),
            "expected_direction": "positive_yes_residual",
            "calibration_null": "E[Y|p,T-6h]=p",
            "economic_null": "mean net payoff <= 0 after ask+fee",
        },
        {
            "model_id": "listing_age_cold_start_fade_extreme_t24h",
            "clock_name": "T-24h",
            "side": "no",
            "feature": "listing_age_hours",
            "direction": "lt_and_p_gt",
            "threshold": 18.0,
            "p_threshold": 0.70,
            "negative_control": False,
            "baseline_only": False,
            "mechanism": (
                "Cold-start / short listing age markets with extreme favorites are "
                "miscalibrated before informed flow arrives."
            ),
            "expected_direction": "favorite_overpriced_when_listing_young",
            "calibration_null": "E[Y|p,listing_age]=p",
            "economic_null": "mean net payoff <= 0 after ask+fee",
        },
        {
            "model_id": "path_slope_reversion_buy_no_t60m",
            "clock_name": "T-60m",
            "side": "no",
            "feature": "path_mid_slope_per_hour",
            "direction": "gt",
            "threshold": 0.015,
            "negative_control": False,
            "baseline_only": False,
            "mechanism": (
                "Steep pregame YES mid run-up measured strictly before T-60m reverts by settlement."
            ),
            "expected_direction": "negative_yes_residual_after_runup",
            "calibration_null": "E[Y|path_slope,T-60m]=p",
            "economic_null": "mean net payoff <= 0 after ask+fee",
        },
        {
            "model_id": "path_slope_continuation_buy_yes_t60m",
            "clock_name": "T-60m",
            "side": "yes",
            "feature": "path_mid_slope_per_hour",
            "direction": "gt",
            "threshold": 0.015,
            "negative_control": False,
            "baseline_only": False,
            "mechanism": (
                "Steep pregame YES mid run-up continues into settlement (opposite of reversion)."
            ),
            "expected_direction": "positive_yes_residual_after_runup",
            "calibration_null": "E[Y|path_slope,T-60m]=p",
            "economic_null": "mean net payoff <= 0 after ask+fee",
        },
        {
            "model_id": "clock_geometry_drift_fade_t15m",
            "clock_name": "T-15m",
            "side": "no",
            "feature": "clock_delta_6h_to_60m",
            "direction": "gt",
            "threshold": 0.04,
            "negative_control": False,
            "baseline_only": False,
            "mechanism": (
                "Large T-6h→T-60m probability lift that remains at T-15m is late overreaction; "
                "fade YES into settlement."
            ),
            "expected_direction": "negative_yes_residual_after_late_lift",
            "calibration_null": "E[Y|clock_geometry]=p",
            "economic_null": "mean net payoff <= 0 after ask+fee",
        },
        {
            "model_id": "tight_spread_favorite_buy_yes_t60m",
            "clock_name": "T-60m",
            "side": "yes",
            "feature": "p_hat",
            "direction": "gt_and_spread_le",
            "threshold": 0.62,
            "spread_max": 0.03,
            "negative_control": False,
            "baseline_only": False,
            "mechanism": (
                "Tight-spread favorites at T-60m are better calibrated / executable than "
                "wide-spread favorites; selective long favorite when friction is low."
            ),
            "expected_direction": "positive_after_fee_when_spread_tight",
            "calibration_null": "E[Y|p,spread]=p",
            "economic_null": "mean net payoff <= 0 after ask+fee",
        },
        {
            "model_id": "negctrl_trade_against_path_slope_t60m",
            "clock_name": "T-60m",
            "side": "yes",
            "feature": "path_mid_slope_per_hour",
            "direction": "lt",
            "threshold": -0.015,
            "negative_control": True,
            "baseline_only": False,
            "mechanism": "Negative control: buy YES after path selloff without theory support.",
            "expected_direction": "should_not_survive_fdr",
            "calibration_null": "E[Y|path]=p",
            "economic_null": "mean net payoff <= 0 after ask+fee",
        },
        {
            "model_id": "negctrl_always_buy_yes_t60m",
            "clock_name": "T-60m",
            "side": "yes",
            "feature": "p_hat",
            "direction": "gt",
            "threshold": 0.01,
            "negative_control": True,
            "baseline_only": False,
            "mechanism": "Negative control: almost always buy YES at T-60m.",
            "expected_direction": "should_not_survive_fdr",
            "calibration_null": "E[Y]=mean(p)",
            "economic_null": "mean net payoff <= 0 after ask+fee",
        },
    ]
