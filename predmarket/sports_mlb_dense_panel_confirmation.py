"""Immutable single-shot confirmation for the registered MLB dense panel.

The preflight is outcome-blind.  It freezes an exact candidate sample only
after every registered panel, candidate-power, breadth, and integrity gate is
met.  Settlement truth is fetched only for that frozen sample.  A durable
attempt may resume after interruption, but it can never expand.  A finalized
result is idempotent and cannot be evaluated again.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from predmarket.shared_helpers import json_float, optional_float, timestamp
from predmarket.sports_mlb_dense_panel import (
    FROZEN_CANDIDATES,
    MAX_SLATE_SHARE,
    MIN_EXECUTABLE_DEPTH_SHARE,
    MIN_PUBLIC_ORDERBOOK_SOURCE_SHARE,
    MIN_SLATES_PER_CANDIDATE,
    PANEL_FAMILY_ID,
    PRIMARY_STALENESS_SECONDS,
    assess_panel_coverage,
    atomic_write_json,
    latest_observed_event_schedule,
    public_orderbook_source_ok,
    snapshot_payload_hash,
)
from predmarket.sports_mlb_settlement_miscalibration import (
    FDR_ALPHA,
    INFERENCE_RESAMPLES,
    INFERENCE_SEED,
    MIN_CONFIRMATION_EVENTS,
    hypothesis_registry,
    microprice,
    resolve_kxmlbgame_taker_fee,
    settlement_outcome,
    sha256_file,
    sha256_text,
)
from predmarket.sports_mlb_settlement_miscalibration_eval import (
    chronological_slate_bucket_means,
    cluster_bootstrap_lower_bound,
    slate_cluster_sign_flip_test,
)

CONTRACT_VERSION = "mlb_dense_panel_single_shot_confirmation_v2"
EXPECTED_PANEL_REGISTRATION_SHA256 = (
    "553135d7d1456aeda4a9115784aa423b81931cceed4d2a2f707b5ca8dcbe816e"
)
EXPECTED_MODEL_ID = "tight_spread_favorite_buy_yes_t60m"
EXPECTED_FORMULA_SHA256 = "9cd76b9703cd167988fd94d53a9cc82ed9b37a7e3b30f316796f9dbb46cfa56d"
CONFIRMATION_CLOCK_SECONDS = 3600
CONFIRMATION_STALENESS_SECONDS = PRIMARY_STALENESS_SECONDS["T-60m"]
SETTLEMENT_BUFFER_SECONDS = 12 * 3600
KALSHI_PUBLIC_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"


def canonical_sha256(payload: Mapping[str, Any]) -> str:
    material = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected JSON object: {path}")
    return dict(payload)


def validate_hashed_payload(
    payload: Mapping[str, Any], *, hash_field: str, expected: str | None = None
) -> tuple[bool, str]:
    given = str(payload.get(hash_field) or "")
    material = dict(payload)
    material.pop(hash_field, None)
    computed = canonical_sha256(material)
    ok = bool(given) and given == computed and (expected is None or given == expected)
    return ok, computed


def frozen_spec() -> dict[str, Any]:
    matches = [row for row in hypothesis_registry() if row.get("model_id") == EXPECTED_MODEL_ID]
    if len(matches) != 1:
        raise ValueError(f"Expected one frozen registry spec, found {len(matches)}")
    return dict(matches[0])


def spec_formula_hash(spec: Mapping[str, Any]) -> str:
    formula = {
        "model_id": spec["model_id"],
        "clock_name": spec["clock_name"],
        "side": spec["side"],
        "feature": spec["feature"],
        "direction": spec["direction"],
        "threshold": spec.get("threshold"),
        "range": spec.get("range"),
        "p_threshold": spec.get("p_threshold"),
        "spread_max": spec.get("spread_max"),
        "mechanism": spec.get("mechanism"),
    }
    return sha256_text(str(sorted(formula.items())))


def build_confirmation_contract(
    *,
    repo_root: Path,
    registered_at_utc: str,
    implementation_paths: Sequence[Path],
) -> dict[str, Any]:
    spec = frozen_spec()
    formula_hash = spec_formula_hash(spec)
    if formula_hash != EXPECTED_FORMULA_SHA256:
        raise ValueError(f"Frozen formula hash drift: {formula_hash}")
    frozen = dict(FROZEN_CANDIDATES[0])
    if frozen.get("model_id") != EXPECTED_MODEL_ID:
        raise ValueError("Dense-panel frozen candidate ID drift")
    if frozen.get("formula_hash") != EXPECTED_FORMULA_SHA256:
        raise ValueError("Dense-panel frozen formula hash drift")
    files = []
    for path in implementation_paths:
        resolved = path.resolve()
        files.append(
            {
                "path": str(resolved.relative_to(repo_root.resolve())),
                "sha256": sha256_file(resolved),
            }
        )
    contract: dict[str, Any] = {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "registered_at_utc": registered_at_utc,
        "panel_family_id": PANEL_FAMILY_ID,
        "panel_registration_sha256": EXPECTED_PANEL_REGISTRATION_SHA256,
        "candidate": {
            "model_id": EXPECTED_MODEL_ID,
            "formula_sha256": EXPECTED_FORMULA_SHA256,
            "clock_name": "T-60m",
            "clock_offset_seconds": CONFIRMATION_CLOCK_SECONDS,
            "side": "yes",
            "feature": "p_hat",
            "direction": "gt_and_spread_le",
            "threshold": float(spec["threshold"]),
            "spread_max": float(spec["spread_max"]),
            "forward_confirmation_registered_at_utc": frozen[
                "forward_confirmation_registered_at_utc"
            ],
        },
        "sample_freeze": {
            "outcome_blind": True,
            "strictly_post_registration": True,
            "freeze_only_after_all_preflight_gates": True,
            "minimum_candidate_events": MIN_CONFIRMATION_EVENTS,
            "minimum_candidate_slate_dates": MIN_SLATES_PER_CANDIDATE,
            "maximum_largest_candidate_slate_share": MAX_SLATE_SHARE,
            "settlement_buffer_seconds": SETTLEMENT_BUFFER_SECONDS,
            "sample_may_never_expand_after_attempt": True,
        },
        "inference": {
            "event_unit": "event_ticker",
            "cluster_unit": "mlb_slate_date_utc",
            "p_economic": "slate_cluster_sign_flip mean fee-adjusted net > 0",
            "p_calibration": "slate_cluster_sign_flip mean selected residual > 0",
            "p_joint": "max(p_economic,p_calibration)",
            "single_candidate_q_value": "q_value=p_joint",
            "alpha": FDR_ALPHA,
            "seed": INFERENCE_SEED,
            "n_resamples": INFERENCE_RESAMPLES,
            "bootstrap_lower_bound_required_above_zero": True,
            "temporal_survival": "at least 3 positive chronological buckets and recent >= 0",
        },
        "candidate_data_quality": {
            "public_orderbook_source_share_min": MIN_PUBLIC_ORDERBOOK_SOURCE_SHARE,
            "executable_depth_share_min": MIN_EXECUTABLE_DEPTH_SHARE,
            "max_staleness_seconds": CONFIRMATION_STALENESS_SECONDS,
            "exact_public_kalshi_settlements_required": True,
            "exact_series_fee_required": True,
        },
        "outcomes": {
            "pass": "research_ready_survivor_research_only",
            "fail": "confirmation_failed",
            "invalid_or_incomplete": "confirmation_pending_no_final_result",
        },
        "durability": {
            "attempt_manifest_created_exclusively": True,
            "interrupted_attempt_resumes_same_sample": True,
            "final_result_idempotent": True,
            "final_result_may_not_be_overwritten": True,
        },
        "implementation_files": files,
        "research_only": True,
        "execution_enabled": False,
        "candidate_performance_revealed_before_final": False,
    }
    contract["contract_sha256"] = canonical_sha256(contract)
    return contract


def validate_contract(contract: Mapping[str, Any], *, repo_root: Path) -> dict[str, Any]:
    contract_hash_ok, computed_hash = validate_hashed_payload(
        contract, hash_field="contract_sha256"
    )
    implementation_checks = []
    for row in contract.get("implementation_files") or []:
        path = repo_root / str(row.get("path") or "")
        expected = str(row.get("sha256") or "")
        actual = sha256_file(path)
        implementation_checks.append(
            {
                "path": str(row.get("path") or ""),
                "expected_sha256": expected,
                "actual_sha256": actual,
                "passed": bool(actual and actual == expected),
            }
        )
    candidate = contract.get("candidate") or {}
    gates = {
        "contract_hash": contract_hash_ok,
        "contract_version": contract.get("contract_version") == CONTRACT_VERSION,
        "panel_registration_hash_pinned": contract.get("panel_registration_sha256")
        == EXPECTED_PANEL_REGISTRATION_SHA256,
        "candidate_id_pinned": candidate.get("model_id") == EXPECTED_MODEL_ID,
        "formula_hash_pinned": candidate.get("formula_sha256") == EXPECTED_FORMULA_SHA256,
        "implementation_hashes": bool(implementation_checks)
        and all(row["passed"] for row in implementation_checks),
    }
    return {
        "passed": all(gates.values()),
        "gates": {key: ("pass" if value else "fail") for key, value in gates.items()},
        "computed_contract_sha256": computed_hash,
        "implementation_checks": implementation_checks,
    }


def load_raw_jsonl_strict(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    invalid_lines: list[int] = []
    non_objects: list[int] = []
    line_count = 0
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            line_count += 1
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                invalid_lines.append(line_number)
                continue
            if not isinstance(payload, Mapping):
                non_objects.append(line_number)
                continue
            rows.append(dict(payload))
    digests = [str(row.get("raw_payload_hash") or snapshot_payload_hash(row)) for row in rows]
    duplicates = {key: count for key, count in Counter(digests).items() if count > 1}
    return rows, {
        "path": str(path),
        "sha256": sha256_file(path),
        "line_count": line_count,
        "parsed_row_count": len(rows),
        "invalid_json_lines": invalid_lines,
        "non_object_lines": non_objects,
        "duplicate_payload_hash_count": len(duplicates),
        "duplicate_payload_row_count": sum(duplicates.values()),
        "passed": not invalid_lines and not non_objects and not duplicates,
    }


def slate_date(game_start_ts: float) -> str:
    return datetime.fromtimestamp(game_start_ts, tz=UTC).strftime("%Y-%m-%d")


def select_frozen_candidate_rows(  # noqa: C901
    rows: Sequence[Mapping[str, Any]], *, registration_utc: str
) -> list[dict[str, Any]]:
    spec = frozen_spec()
    boundary = timestamp(registration_utc)
    if boundary is None:
        raise ValueError("Invalid forward registration timestamp")
    by_event: dict[str, list[dict[str, Any]]] = {}
    for raw in rows:
        ticker = str(raw.get("contract_ticker") or "")
        observed_ts = timestamp(raw.get("observed_at_utc"))
        if not ticker.startswith("KXMLBGAME") or observed_ts is None:
            continue
        item = dict(raw)
        item["observed_ts"] = observed_ts
        event = str(raw.get("event_ticker") or ticker.rsplit("-", 1)[0])
        item["event_ticker"] = event
        by_event.setdefault(event, []).append(item)

    candidates: list[dict[str, Any]] = []
    for event in sorted(by_event):
        game_start, current_schedule_rows = latest_observed_event_schedule(by_event[event])
        if game_start is None:
            continue
        decision_ts = game_start - CONFIRMATION_CLOCK_SECONDS
        if decision_ts <= float(boundary):
            continue
        by_ticker: dict[str, list[dict[str, Any]]] = {}
        for row in current_schedule_rows:
            ticker = str(row.get("contract_ticker") or "")
            by_ticker.setdefault(ticker, []).append(row)
        for ticker in sorted(by_ticker):
            eligible = [
                row
                for row in by_ticker[ticker]
                if row.get("schedule_revision") is not True
                and float(row["observed_ts"]) <= decision_ts
                and decision_ts - float(row["observed_ts"]) <= CONFIRMATION_STALENESS_SECONDS
            ]
            if not eligible:
                continue
            book = max(
                eligible,
                key=lambda row: (float(row["observed_ts"]), str(row.get("snapshot_id"))),
            )
            yes_bid = optional_float(book.get("best_yes_bid"))
            yes_ask = optional_float(book.get("best_yes_ask"))
            if yes_bid is None or yes_ask is None or not (0 < yes_bid <= yes_ask < 1):
                continue
            spread = optional_float(book.get("yes_spread"))
            if spread is None:
                spread = yes_ask - yes_bid
            p_hat = microprice(
                yes_bid,
                yes_ask,
                optional_float(book.get("yes_bid_depth_top1")),
                optional_float(book.get("yes_ask_depth_top1")),
            )
            if p_hat is None:
                p_hat = (yes_bid + yes_ask) / 2.0
            if not (p_hat > float(spec["threshold"]) and spread <= float(spec["spread_max"])):
                continue
            candidates.append(
                {
                    "contract_ticker": ticker,
                    "event_ticker": event,
                    "clock_name": "T-60m",
                    "decision_ts": decision_ts,
                    "game_start_ts": game_start,
                    "game_start_resolution": "latest_observed_start_per_event",
                    "slate_date": slate_date(game_start),
                    "book_observed_at_utc": book.get("observed_at_utc"),
                    "book_observed_ts": float(book["observed_ts"]),
                    "book_age_seconds": decision_ts - float(book["observed_ts"]),
                    "snapshot_id": book.get("snapshot_id"),
                    "raw_payload_hash": book.get("raw_payload_hash") or snapshot_payload_hash(book),
                    "entry_source": book.get("entry_source"),
                    "public_orderbook_source_ok": public_orderbook_source_ok(book),
                    "best_yes_bid": yes_bid,
                    "best_yes_ask": yes_ask,
                    "yes_bid_depth_top1": optional_float(book.get("yes_bid_depth_top1")),
                    "yes_ask_depth_top1": optional_float(book.get("yes_ask_depth_top1")),
                    "p_hat": p_hat,
                    "yes_spread": spread,
                    "research_only": True,
                    "execution_enabled": False,
                }
            )

    # Match the discovery evaluator's event-level independence discipline.
    selected_by_event: dict[str, dict[str, Any]] = {}
    for row in sorted(candidates, key=lambda item: (item["decision_ts"], item["contract_ticker"])):
        selected_by_event.setdefault(str(row["event_ticker"]), row)
    return sorted(
        selected_by_event.values(),
        key=lambda item: (item["decision_ts"], item["event_ticker"]),
    )


def confirmation_preflight(
    *,
    raw_path: Path,
    registration_path: Path,
    contract_path: Path,
    state_dir: Path,
    repo_root: Path,
    now_utc: str,
) -> dict[str, Any]:
    registration = load_json_object(registration_path)
    registration_ok, computed_registration_hash = validate_hashed_payload(
        registration,
        hash_field="registration_sha256",
        expected=EXPECTED_PANEL_REGISTRATION_SHA256,
    )
    contract = load_json_object(contract_path)
    contract_validation = validate_contract(contract, repo_root=repo_root)
    rows, raw_integrity = load_raw_jsonl_strict(raw_path)
    coverage = assess_panel_coverage(rows)
    frozen = contract.get("candidate") or {}
    registration_utc = str(frozen.get("forward_confirmation_registered_at_utc") or "")
    candidates = select_frozen_candidate_rows(rows, registration_utc=registration_utc)
    slate_counts = Counter(str(row["slate_date"]) for row in candidates)
    largest_share = max(slate_counts.values()) / len(candidates) if candidates else 1.0
    source_share = (
        sum(1 for row in candidates if row["public_orderbook_source_ok"]) / len(candidates)
        if candidates
        else 0.0
    )
    depth_share = (
        sum(
            1
            for row in candidates
            if optional_float(row.get("yes_ask_depth_top1")) is not None
            and float(row["yes_ask_depth_top1"]) > 0
        )
        / len(candidates)
        if candidates
        else 0.0
    )
    now_ts = timestamp(now_utc)
    buffer_elapsed = bool(
        candidates
        and now_ts is not None
        and now_ts
        >= max(float(row["game_start_ts"]) for row in candidates) + SETTLEMENT_BUFFER_SECONDS
    )
    attempt_path = state_dir / "single-shot-attempt.json"
    final_path = state_dir / "single-shot-final.json"
    gates = {
        "registration_hash": registration_ok,
        "contract_validation": bool(contract_validation.get("passed")),
        "raw_integrity": bool(raw_integrity.get("passed")),
        "panel_evidence_ready": bool(coverage.get("evidence_panel_ready")),
        "candidate_min_events": len(candidates) >= MIN_CONFIRMATION_EVENTS,
        "candidate_min_slate_dates": len(slate_counts) >= MIN_SLATES_PER_CANDIDATE,
        "candidate_largest_slate_share": largest_share <= MAX_SLATE_SHARE,
        "candidate_public_orderbook_share": source_share >= MIN_PUBLIC_ORDERBOOK_SOURCE_SHARE,
        "candidate_executable_depth_share": depth_share >= MIN_EXECUTABLE_DEPTH_SHARE,
        "candidate_strictly_post_registration": bool(candidates)
        and all(
            float(row["decision_ts"]) > float(timestamp(registration_utc) or 0)
            for row in candidates
        ),
        "candidate_settlement_buffer_elapsed": buffer_elapsed,
    }
    start_ready = all(gates.values()) and not attempt_path.exists() and not final_path.exists()
    if final_path.exists():
        status = "confirmation_finalized"
    elif attempt_path.exists():
        status = "single_shot_sample_already_frozen"
    elif start_ready:
        status = "ready_to_freeze_single_shot_sample"
    else:
        status = "confirmation_pending"
    return {
        "status": status,
        "generated_utc": now_utc,
        "confirmation_start_ready": start_ready,
        "candidate_performance_revealed": False,
        "gates": {key: ("pass" if value else "fail") for key, value in gates.items()},
        "coverage": coverage,
        "candidate_sample": {
            "event_count": len(candidates),
            "slate_date_count": len(slate_counts),
            "largest_slate_share": json_float(largest_share),
            "public_orderbook_source_share": json_float(source_share),
            "executable_depth_share": json_float(depth_share),
            "settlement_buffer_elapsed": buffer_elapsed,
        },
        "raw_integrity": raw_integrity,
        "registration_validation": {
            "passed": registration_ok,
            "expected_sha256": EXPECTED_PANEL_REGISTRATION_SHA256,
            "computed_sha256": computed_registration_hash,
        },
        "contract_validation": contract_validation,
        "state": {
            "attempt_exists": attempt_path.exists(),
            "final_exists": final_path.exists(),
            "state_dir": str(state_dir),
        },
        "_candidate_rows": candidates,
        "_contract": contract,
        "research_only": True,
        "execution_enabled": False,
    }


def public_preflight_payload(preflight: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in preflight.items() if not str(key).startswith("_")}


def freeze_single_shot_attempt(
    *, preflight: Mapping[str, Any], state_dir: Path, started_at_utc: str
) -> dict[str, Any]:
    if not preflight.get("confirmation_start_ready"):
        raise ValueError("Confirmation preflight is not ready")
    state_dir.mkdir(parents=True, exist_ok=True)
    attempt_path = state_dir / "single-shot-attempt.json"
    rows = list(preflight.get("_candidate_rows") or [])
    contract = preflight.get("_contract") or {}
    material = {
        "contract_sha256": contract.get("contract_sha256"),
        "raw_sha256": (preflight.get("raw_integrity") or {}).get("sha256"),
        "candidate_rows": rows,
    }
    attempt = {
        "schema_version": 1,
        "attempt_id": canonical_sha256(material),
        "status": "sample_frozen_outcomes_unread",
        "started_at_utc": started_at_utc,
        "contract_sha256": contract.get("contract_sha256"),
        "panel_registration_sha256": EXPECTED_PANEL_REGISTRATION_SHA256,
        "formula_sha256": EXPECTED_FORMULA_SHA256,
        "sample_raw_sha256": (preflight.get("raw_integrity") or {}).get("sha256"),
        "candidate_event_count": len(rows),
        "candidate_slate_date_count": len({row["slate_date"] for row in rows}),
        "candidate_rows": rows,
        "sample_may_never_expand": True,
        "settlement_outcomes_read": False,
        "candidate_performance_revealed": False,
        "research_only": True,
        "execution_enabled": False,
    }
    attempt["attempt_sha256"] = canonical_sha256(attempt)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(attempt_path, flags, 0o600)
    try:
        os.write(fd, (json.dumps(attempt, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    return attempt


def validate_attempt(attempt: Mapping[str, Any], *, contract_sha256: str) -> dict[str, Any]:
    hash_ok, computed_hash = validate_hashed_payload(attempt, hash_field="attempt_sha256")
    material = {
        "contract_sha256": attempt.get("contract_sha256"),
        "raw_sha256": attempt.get("sample_raw_sha256"),
        "candidate_rows": attempt.get("candidate_rows") or [],
    }
    gates = {
        "attempt_hash": hash_ok,
        "attempt_id": attempt.get("attempt_id") == canonical_sha256(material),
        "contract_hash": attempt.get("contract_sha256") == contract_sha256,
        "panel_registration_hash": attempt.get("panel_registration_sha256")
        == EXPECTED_PANEL_REGISTRATION_SHA256,
        "formula_hash": attempt.get("formula_sha256") == EXPECTED_FORMULA_SHA256,
        "event_count": int(attempt.get("candidate_event_count") or 0)
        == len(attempt.get("candidate_rows") or []),
        "sample_immutable": attempt.get("sample_may_never_expand") is True,
    }
    return {
        "passed": all(gates.values()),
        "gates": {key: ("pass" if value else "fail") for key, value in gates.items()},
        "computed_attempt_sha256": computed_hash,
    }


def resolve_frozen_attempt_fees(
    attempt: Mapping[str, Any],
    *,
    fee_resolver: Callable[..., Mapping[str, Any]] = resolve_kxmlbgame_taker_fee,
) -> tuple[dict[str, dict[str, Any]], bool]:
    fee_by_ticker: dict[str, dict[str, Any]] = {}
    for decision in attempt.get("candidate_rows") or []:
        ticker = str(decision.get("contract_ticker") or "")
        ask = float(decision["best_yes_ask"])
        fee_by_ticker[ticker] = dict(
            fee_resolver(
                ask,
                contract_count=1.0,
                series_ticker="KXMLBGAME",
                as_of_ts=float(decision["book_observed_ts"]),
                allow_network=True,
            )
        )
    exact = bool(fee_by_ticker) and all(
        str(row.get("fee_fallback_state") or "none") == "none" for row in fee_by_ticker.values()
    )
    return fee_by_ticker, exact


def fetch_public_market(ticker: str, *, timeout: float = 30.0) -> dict[str, Any]:
    url = f"{KALSHI_PUBLIC_BASE_URL}/markets/{urllib.parse.quote(ticker, safe='')}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "predmarket-research-mlb-single-shot-confirmation/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    market = payload.get("market") if isinstance(payload, Mapping) else None
    if not isinstance(market, Mapping):
        raise ValueError(f"Missing market payload for {ticker}")
    return dict(market)


def fetch_frozen_settlements(
    attempt: Mapping[str, Any],
    *,
    fetcher: Callable[[str], Mapping[str, Any]] = fetch_public_market,
    request_delay_seconds: float = 0.08,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    settlements: dict[str, dict[str, Any]] = {}
    unresolved: list[str] = []
    for row in attempt.get("candidate_rows") or []:
        ticker = str(row.get("contract_ticker") or "")
        market = dict(fetcher(ticker))
        returned = str(market.get("ticker") or market.get("contract_ticker") or "")
        outcome = settlement_outcome(market)
        if returned != ticker or outcome is None:
            unresolved.append(ticker)
        else:
            market["contract_ticker"] = ticker
            market["yes_outcome"] = int(outcome)
            settlements[ticker] = market
        if request_delay_seconds > 0:
            time.sleep(request_delay_seconds)
    return settlements, unresolved


def evaluate_frozen_attempt(
    attempt: Mapping[str, Any],
    settlements: Mapping[str, Mapping[str, Any]],
    *,
    fee_resolver: Callable[..., Mapping[str, Any]] = resolve_kxmlbgame_taker_fee,
    fee_by_ticker: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    event_rows: list[dict[str, Any]] = []
    fee_rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for decision in attempt.get("candidate_rows") or []:
        ticker = str(decision.get("contract_ticker") or "")
        market = settlements.get(ticker)
        outcome = settlement_outcome(market or {})
        if outcome is None:
            missing.append(ticker)
            continue
        ask = float(decision["best_yes_ask"])
        fee = dict((fee_by_ticker or {}).get(ticker) or {})
        if not fee:
            fee = dict(
                fee_resolver(
                    ask,
                    contract_count=1.0,
                    series_ticker="KXMLBGAME",
                    as_of_ts=float(decision["book_observed_ts"]),
                    allow_network=True,
                )
            )
        fee_rows.append(fee)
        net = float(outcome) - ask - float(fee["fee"])
        residual = float(outcome) - float(decision["p_hat"])
        event_rows.append(
            {
                **dict(decision),
                "yes_outcome": int(outcome),
                "selected_net_return": net,
                "selected_calibration_residual": residual,
                "selected_capacity": decision.get("yes_ask_depth_top1"),
            }
        )
    if missing:
        return {
            "status": "confirmation_pending_incomplete_settlements",
            "missing_settlement_count": len(missing),
            "candidate_performance_revealed": False,
            "finalizable": False,
        }

    exact_fee = bool(fee_rows) and all(
        str(row.get("fee_fallback_state") or "none") == "none" for row in fee_rows
    )
    economic = slate_cluster_sign_flip_test(
        event_rows,
        "selected_net_return",
        seed=INFERENCE_SEED,
        n_resamples=INFERENCE_RESAMPLES,
    )
    calibration = slate_cluster_sign_flip_test(
        event_rows,
        "selected_calibration_residual",
        seed=INFERENCE_SEED + 17,
        n_resamples=INFERENCE_RESAMPLES,
    )
    bootstrap = cluster_bootstrap_lower_bound(
        event_rows, "selected_net_return", seed=INFERENCE_SEED
    )
    temporal = chronological_slate_bucket_means(event_rows, "selected_net_return")
    nets = [float(row["selected_net_return"]) for row in event_rows]
    residuals = [float(row["selected_calibration_residual"]) for row in event_rows]
    slate_counts = Counter(str(row["slate_date"]) for row in event_rows)
    largest_share = max(slate_counts.values()) / len(event_rows) if event_rows else 1.0
    source_share = (
        sum(1 for row in event_rows if row["public_orderbook_source_ok"]) / len(event_rows)
        if event_rows
        else 0.0
    )
    depth_share = (
        sum(
            1
            for row in event_rows
            if optional_float(row.get("yes_ask_depth_top1")) is not None
            and float(row["yes_ask_depth_top1"]) > 0
        )
        / len(event_rows)
        if event_rows
        else 0.0
    )
    p_economic = float(economic.get("p_value") or 1.0)
    p_calibration = float(calibration.get("p_value") or 1.0)
    p_joint = max(p_economic, p_calibration)
    mean_net = sum(nets) / len(nets) if nets else None
    mean_residual = sum(residuals) / len(residuals) if residuals else None
    recent = optional_float(temporal.get("recent_bucket_mean"))
    validity_gates = {
        "all_settlements_exact": len(event_rows) == int(attempt.get("candidate_event_count") or 0),
        "exact_series_fee": exact_fee,
        "event_power": len(event_rows) >= MIN_CONFIRMATION_EVENTS,
        "slate_power": len(slate_counts) >= MIN_SLATES_PER_CANDIDATE,
        "largest_slate_share": largest_share <= MAX_SLATE_SHARE,
        "public_orderbook_source_share": source_share >= MIN_PUBLIC_ORDERBOOK_SOURCE_SHARE,
        "executable_depth_share": depth_share >= MIN_EXECUTABLE_DEPTH_SHARE,
    }
    outcome_gates = {
        "positive_mean_net": mean_net is not None and mean_net > 0,
        "positive_mean_calibration_residual": mean_residual is not None and mean_residual > 0,
        "economic_inference": p_economic <= FDR_ALPHA,
        "calibration_inference": p_calibration <= FDR_ALPHA,
        "single_candidate_q_value": p_joint <= FDR_ALPHA,
        "bootstrap_lower_bound_above_zero": optional_float(bootstrap.get("lower_bound")) is not None
        and float(bootstrap["lower_bound"]) > 0,
        "temporal_survival": int(temporal.get("positive_buckets") or 0) >= 3
        and (recent is None or recent >= 0),
    }
    validity_passed = all(validity_gates.values())
    if not validity_passed:
        status = "confirmation_pending_invalid_or_incomplete_evidence"
        finalizable = False
    elif all(outcome_gates.values()):
        status = "research_ready_survivor_research_only"
        finalizable = True
    else:
        status = "confirmation_failed"
        finalizable = True
    return {
        "status": status,
        "finalizable": finalizable,
        "attempt_id": attempt.get("attempt_id"),
        "model_id": EXPECTED_MODEL_ID,
        "formula_sha256": EXPECTED_FORMULA_SHA256,
        "event_count": len(event_rows),
        "slate_date_count": len(slate_counts),
        "slate_counts": dict(sorted(slate_counts.items())),
        "largest_slate_share": json_float(largest_share),
        "mean_net_return": json_float(mean_net),
        "mean_calibration_residual": json_float(mean_residual),
        "positive_rate_descriptive_only": json_float(
            sum(1 for value in nets if value > 0) / len(nets) if nets else None
        ),
        "p_economic": json_float(p_economic),
        "p_calibration": json_float(p_calibration),
        "p_joint": json_float(p_joint),
        "q_value": json_float(p_joint),
        "economic_inference": economic,
        "calibration_inference": calibration,
        "bootstrap_inference": bootstrap,
        "temporal_inference": temporal,
        "public_orderbook_source_share": json_float(source_share),
        "executable_depth_share": json_float(depth_share),
        "fee_provenance": fee_rows,
        "validity_gates": {
            key: ("pass" if value else "fail") for key, value in validity_gates.items()
        },
        "outcome_gates": {
            key: ("pass" if value else "fail") for key, value in outcome_gates.items()
        },
        "candidate_performance_revealed": True,
        "research_only": True,
        "execution_enabled": False,
        "paper_or_live_promotion_authorized": False,
    }


def run_single_shot_confirmation(
    *,
    preflight: Mapping[str, Any],
    state_dir: Path,
    now_utc: str,
    fetcher: Callable[[str], Mapping[str, Any]] = fetch_public_market,
    fee_resolver: Callable[..., Mapping[str, Any]] = resolve_kxmlbgame_taker_fee,
    request_delay_seconds: float = 0.08,
) -> dict[str, Any]:
    final_path = state_dir / "single-shot-final.json"
    attempt_path = state_dir / "single-shot-attempt.json"
    if final_path.exists():
        result = load_json_object(final_path)
        final_ok, _computed = validate_hashed_payload(result, hash_field="final_sha256")
        if not final_ok:
            raise ValueError("Final confirmation sentinel hash mismatch")
        result["idempotent_replay"] = True
        return result
    if attempt_path.exists():
        attempt = load_json_object(attempt_path)
    else:
        if not preflight.get("confirmation_start_ready"):
            return {
                **public_preflight_payload(preflight),
                "status": "confirmation_pending_preflight_not_ready",
            }
        attempt = freeze_single_shot_attempt(
            preflight=preflight, state_dir=state_dir, started_at_utc=now_utc
        )

    contract_sha = str((preflight.get("_contract") or {}).get("contract_sha256") or "")
    attempt_validation = validate_attempt(attempt, contract_sha256=contract_sha)
    if not attempt_validation["passed"]:
        return {
            "status": "confirmation_pending_attempt_integrity_failed",
            "attempt_validation": attempt_validation,
            "candidate_performance_revealed": False,
            "research_only": True,
            "execution_enabled": False,
        }

    fee_by_ticker, exact_fee = resolve_frozen_attempt_fees(attempt, fee_resolver=fee_resolver)
    atomic_write_json(
        state_dir / "fee-evidence.json",
        {
            "generated_utc": now_utc,
            "attempt_id": attempt.get("attempt_id"),
            "exact_series_fee": exact_fee,
            "fee_by_ticker": fee_by_ticker,
            "candidate_performance_revealed": False,
            "research_only": True,
            "execution_enabled": False,
        },
    )
    if not exact_fee:
        return {
            "status": "single_shot_sample_frozen_waiting_exact_series_fee",
            "attempt_id": attempt.get("attempt_id"),
            "candidate_event_count": attempt.get("candidate_event_count"),
            "candidate_performance_revealed": False,
            "research_only": True,
            "execution_enabled": False,
        }

    settlements, unresolved = fetch_frozen_settlements(
        attempt, fetcher=fetcher, request_delay_seconds=request_delay_seconds
    )
    fetch_dir = state_dir / "settlement-fetches"
    fetch_dir.mkdir(parents=True, exist_ok=True)
    stamp = now_utc.replace(":", "").replace("-", "")
    settlement_evidence_path = fetch_dir / f"settlements-{stamp}.json"
    atomic_write_json(
        settlement_evidence_path,
        {
            "generated_utc": now_utc,
            "attempt_id": attempt.get("attempt_id"),
            "settlements": list(settlements.values()),
            "unresolved_tickers": unresolved,
            "research_only": True,
            "execution_enabled": False,
        },
    )
    if unresolved:
        return {
            "status": "single_shot_sample_frozen_waiting_exact_settlements",
            "attempt_id": attempt.get("attempt_id"),
            "candidate_event_count": attempt.get("candidate_event_count"),
            "resolved_settlement_count": len(settlements),
            "unresolved_settlement_count": len(unresolved),
            "settlement_evidence_path": str(settlement_evidence_path),
            "settlement_evidence_sha256": sha256_file(settlement_evidence_path),
            "sample_may_never_expand": True,
            "candidate_performance_revealed": False,
            "research_only": True,
            "execution_enabled": False,
        }

    result = evaluate_frozen_attempt(
        attempt,
        settlements,
        fee_resolver=fee_resolver,
        fee_by_ticker=fee_by_ticker,
    )
    result["generated_utc"] = now_utc
    result["contract_sha256"] = attempt.get("contract_sha256")
    result["panel_registration_sha256"] = attempt.get("panel_registration_sha256")
    result["attempt_sha256"] = attempt.get("attempt_sha256")
    result["sample_raw_sha256"] = attempt.get("sample_raw_sha256")
    result["settlement_evidence_path"] = str(settlement_evidence_path)
    result["settlement_evidence_sha256"] = sha256_file(settlement_evidence_path)
    if result.get("finalizable"):
        result["final_sha256"] = canonical_sha256(result)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(final_path, flags, 0o600)
        try:
            os.write(fd, (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    return result


__all__ = [
    "CONTRACT_VERSION",
    "EXPECTED_FORMULA_SHA256",
    "EXPECTED_PANEL_REGISTRATION_SHA256",
    "build_confirmation_contract",
    "confirmation_preflight",
    "evaluate_frozen_attempt",
    "freeze_single_shot_attempt",
    "public_preflight_payload",
    "resolve_frozen_attempt_fees",
    "run_single_shot_confirmation",
    "select_frozen_candidate_rows",
    "validate_attempt",
    "validate_contract",
]
