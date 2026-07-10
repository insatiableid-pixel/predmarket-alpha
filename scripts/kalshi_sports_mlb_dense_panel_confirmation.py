#!/usr/bin/env python3
"""Register, preflight, and run the MLB dense-panel single-shot confirmation.

`preflight` is outcome-blind. `run` cannot fetch settlement truth until every
registered readiness and candidate-power gate passes. No sizing or execution.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import manual_drop_path, utc_now  # noqa: E402
from predmarket.sports_mlb_dense_panel import atomic_write_json, atomic_write_text  # noqa: E402
from predmarket.sports_mlb_dense_panel_confirmation import (  # noqa: E402
    build_confirmation_contract,
    confirmation_preflight,
    public_preflight_payload,
    run_single_shot_confirmation,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_REGISTRATION_PATH = MACRO_DIR / "latest-kalshi-sports-mlb-dense-panel-registration.json"
DEFAULT_CONTRACT_PATH = (
    MACRO_DIR / "latest-kalshi-sports-mlb-dense-panel-confirmation-contract.json"
)
DEFAULT_CONTRACT_MD_PATH = (
    MACRO_DIR / "latest-kalshi-sports-mlb-dense-panel-confirmation-contract.md"
)
DEFAULT_RAW_PATH = manual_drop_path(
    "kalshi_sports_mlb_dense_panel_raw/mlb_dense_panel_snapshots.jsonl",
    env_vars=("KALSHI_SPORTS_MLB_DENSE_PANEL_RAW_JSONL",),
)
DEFAULT_STATE_DIR = manual_drop_path(
    "kalshi_sports_mlb_dense_panel_confirmation",
    env_vars=("KALSHI_SPORTS_MLB_DENSE_PANEL_CONFIRMATION_DIR",),
)
IMPLEMENTATION_PATHS = (
    CONTROL_REPO / "predmarket" / "sports_mlb_dense_panel.py",
    CONTROL_REPO / "predmarket" / "sports_mlb_dense_panel_confirmation.py",
    CONTROL_REPO / "scripts" / "kalshi_sports_mlb_dense_book_capture.py",
    CONTROL_REPO / "scripts" / "kalshi_sports_mlb_dense_panel_ops.py",
    Path(__file__).resolve(),
)


def render_contract_markdown(contract: Mapping[str, Any]) -> str:
    candidate = contract.get("candidate") or {}
    sample = contract.get("sample_freeze") or {}
    inference = contract.get("inference") or {}
    return "\n".join(
        [
            "# MLB Dense-Panel Single-Shot Confirmation Contract",
            "",
            f"- Contract: `{contract.get('contract_version')}`",
            f"- Registered: `{contract.get('registered_at_utc')}`",
            f"- Contract hash: `{contract.get('contract_sha256')}`",
            f"- Panel registration hash: `{contract.get('panel_registration_sha256')}`",
            f"- Candidate: `{candidate.get('model_id')}`",
            f"- Formula hash: `{candidate.get('formula_sha256')}`",
            f"- Clock / side: `{candidate.get('clock_name')}` / `{candidate.get('side')}`",
            f"- Threshold / spread max: `{candidate.get('threshold')}` / `{candidate.get('spread_max')}`",
            f"- Minimum events / slates: `{sample.get('minimum_candidate_events')}` / `{sample.get('minimum_candidate_slate_dates')}`",
            f"- Maximum slate share: `{sample.get('maximum_largest_candidate_slate_share')}`",
            f"- Inference: `{inference.get('p_joint')}`; alpha=`{inference.get('alpha')}`",
            "",
            "The candidate sample is frozen before settlement fetches. Interrupted runs",
            "resume the same sample; finalized results are idempotent and immutable.",
            "",
            "Research-only. No paper/live promotion, sizing, accounts, or orders.",
            "",
        ]
    )


def cmd_contract(
    *, contract_path: Path, markdown_path: Path, registered_at_utc: str, force: bool
) -> dict[str, Any]:
    if contract_path.exists() and not force:
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
        return {
            "status": "confirmation_contract_already_exists",
            "contract_sha256": payload.get("contract_sha256"),
            "path": str(contract_path),
            "research_only": True,
            "execution_enabled": False,
        }
    contract = build_confirmation_contract(
        repo_root=CONTROL_REPO,
        registered_at_utc=registered_at_utc,
        implementation_paths=IMPLEMENTATION_PATHS,
    )
    atomic_write_json(contract_path, contract)
    atomic_write_text(markdown_path, render_contract_markdown(contract))
    return {
        "status": "confirmation_contract_registered_outcome_blind",
        "contract_sha256": contract.get("contract_sha256"),
        "path": str(contract_path),
        "markdown_path": str(markdown_path),
        "research_only": True,
        "execution_enabled": False,
    }


def build_preflight(
    *, raw_path: Path, registration_path: Path, contract_path: Path, state_dir: Path, now_utc: str
) -> dict[str, Any]:
    return confirmation_preflight(
        raw_path=raw_path,
        registration_path=registration_path,
        contract_path=contract_path,
        state_dir=state_dir,
        repo_root=CONTROL_REPO,
        now_utc=now_utc,
    )


def cmd_preflight(**kwargs: Any) -> dict[str, Any]:
    preflight = build_preflight(**kwargs)
    public = public_preflight_payload(preflight)
    state_dir = Path(kwargs["state_dir"])
    state_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(state_dir / "preflight-latest.json", public)
    return public


def cmd_run(**kwargs: Any) -> dict[str, Any]:
    preflight = build_preflight(**kwargs)
    result = run_single_shot_confirmation(
        preflight=preflight,
        state_dir=Path(kwargs["state_dir"]),
        now_utc=str(kwargs["now_utc"]),
    )
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    contract = sub.add_parser("contract", help="Register immutable execution contract")
    contract.add_argument("--contract-path", type=Path, default=DEFAULT_CONTRACT_PATH)
    contract.add_argument("--markdown-path", type=Path, default=DEFAULT_CONTRACT_MD_PATH)
    contract.add_argument("--registered-at-utc", default=None)
    contract.add_argument("--force", action="store_true")

    for name in ("preflight", "run"):
        command = sub.add_parser(name, help=f"{name.title()} single-shot confirmation")
        command.add_argument("--raw-path", type=Path, default=DEFAULT_RAW_PATH)
        command.add_argument("--registration-path", type=Path, default=DEFAULT_REGISTRATION_PATH)
        command.add_argument("--contract-path", type=Path, default=DEFAULT_CONTRACT_PATH)
        command.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
        command.add_argument("--now-utc", default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "contract":
            result = cmd_contract(
                contract_path=args.contract_path,
                markdown_path=args.markdown_path,
                registered_at_utc=args.registered_at_utc or utc_now(),
                force=bool(args.force),
            )
        else:
            kwargs = {
                "raw_path": args.raw_path,
                "registration_path": args.registration_path,
                "contract_path": args.contract_path,
                "state_dir": args.state_dir,
                "now_utc": args.now_utc or utc_now(),
            }
            result = cmd_preflight(**kwargs) if args.command == "preflight" else cmd_run(**kwargs)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
