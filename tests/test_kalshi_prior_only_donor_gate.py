from __future__ import annotations

import json
import tempfile
from pathlib import Path

from predmarket.prior_only_donor import build_prior_only_donor_gate
from predmarket.source_inventory import SourceRepoDescriptor
from scripts.kalshi_external_artifact_preflight import build_external_artifact_preflight
from scripts.kalshi_prior_only_donor_gate import write_report
from scripts.kalshi_signal_formula_registry import build_registry_report, write_registry

MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def raw_safe_donor(*rows: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "raw_donor_ready",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "rows": list(rows),
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
        },
    }


def preflight_for_raw(raw: Path, wrap_root: Path, generated_utc: str) -> dict[str, object]:
    descriptor = SourceRepoDescriptor(
        repo_id="unit-donor",
        path=str(raw.parent),
        donor_type="model-output",
        admission_status="admit_prior_only_context",
        family_ids=("thin_sports_family",),
        admissible_artifacts=(str(raw),),
    )
    return build_external_artifact_preflight(
        generated_utc=generated_utc,
        wrap_root=wrap_root,
        descriptors=(descriptor,),
    )


def test_prior_only_gate_admits_donor_probability_only_as_context(tmp_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="prior-donor-", dir="/tmp") as external_dir:
        raw = Path(external_dir) / "donor.json"
        write_json(
            raw,
            raw_safe_donor(
                {
                    "contract_ticker": "KXUNIT-YES",
                    "side": "yes",
                    "calibrated_probability": 0.61,
                    "market_probability": 0.55,
                }
            ),
        )
        preflight = preflight_for_raw(raw, tmp_path / "wrapped", "2026-07-05T00:00:00Z")
        preflight_path = tmp_path / "preflight.json"
        registry = build_registry_report(generated_utc="2026-07-05T00:00:00Z")
        registry_path = tmp_path / "registry.json"
        write_json(preflight_path, preflight)
        write_json(registry_path, registry)

        report = build_prior_only_donor_gate(
            external_preflight_path=preflight_path,
            formula_registry_path=registry_path,
            generated_utc="2026-07-05T00:00:00Z",
        )

    row = report["prior_context_rows"][0]
    assert report["status"] == "prior_only_donor_gate_ready"
    assert row["prior_probability"] == 0.61
    assert row["calibrated_probability"] is None
    assert row["expected_value_per_contract"] is None
    assert row["counts_toward_independent_labels"] is False
    assert row["counts_toward_oos_labels"] is False
    assert row["paper_stake"] == 0.0
    assert row["paper_usable"] is False
    assert row["live_eligible"] is False
    assert report["summary"]["settlement_label_credit_count"] == 0
    assert report["summary"]["multiple_testing_ready_formula_count"] == 2


def test_prior_only_gate_blocks_label_like_donor_rows(tmp_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="prior-donor-", dir="/tmp") as external_dir:
        raw = Path(external_dir) / "donor.json"
        write_json(
            raw,
            raw_safe_donor(
                {
                    "contract_ticker": "KXUNIT-YES",
                    "side": "yes",
                    "model_probability": 0.61,
                    "settlement_result": "win",
                }
            ),
        )
        preflight = preflight_for_raw(raw, tmp_path / "wrapped", "2026-07-05T00:00:00Z")
        preflight_path = tmp_path / "preflight.json"
        write_json(preflight_path, preflight)

        report = build_prior_only_donor_gate(
            external_preflight_path=preflight_path,
            generated_utc="2026-07-05T00:00:00Z",
        )

    row = report["prior_context_rows"][0]
    assert report["status"] == "prior_only_donor_gate_ready_all_context_blocked"
    assert row["status"] == "prior_context_blocked"
    assert "row has label/outcome-like payload" in row["blocker_list"][0]
    assert row["counts_toward_settlement_labels"] is False
    assert report["summary"]["independent_label_credit_count"] == 0


def test_prior_only_gate_blocks_direct_ev_or_paper_promotion_fields(tmp_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="prior-donor-", dir="/tmp") as external_dir:
        raw = Path(external_dir) / "donor.json"
        write_json(
            raw,
            raw_safe_donor(
                {
                    "contract_ticker": "KXUNIT-YES",
                    "side": "yes",
                    "model_probability": 0.61,
                    "expected_value_per_contract": 0.04,
                }
            ),
        )
        preflight = preflight_for_raw(raw, tmp_path / "wrapped", "2026-07-05T00:00:00Z")
        preflight_path = tmp_path / "preflight.json"
        write_json(preflight_path, preflight)

        report = build_prior_only_donor_gate(
            external_preflight_path=preflight_path,
            generated_utc="2026-07-05T00:00:00Z",
        )

    row = report["prior_context_rows"][0]
    assert row["status"] == "prior_context_blocked"
    assert "direct promotion" in "; ".join(row["blocker_list"])
    assert row["expected_value_per_contract"] is None
    assert row["paper_usable"] is False


def test_prior_only_gate_cli_writer_and_makefile_wiring(tmp_path: Path) -> None:
    preflight_path = tmp_path / "preflight.json"
    registry_path = tmp_path / "registry.json"
    write_json(
        preflight_path,
        {
            "schema_version": 1,
            "status": "external_artifact_preflight_ready",
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "artifacts": [],
            "safety": {
                "research_only": True,
                "execution_enabled": False,
                "database_writes": False,
                "market_execution": False,
                "account_or_order_paths": False,
            },
        },
    )
    write_registry(
        build_registry_report(generated_utc="2026-07-05T00:00:00Z"), tmp_path / "registry"
    )
    registry_path.write_text((tmp_path / "registry" / "signal-formula-registry.json").read_text())
    report = build_prior_only_donor_gate(
        external_preflight_path=preflight_path,
        formula_registry_path=registry_path,
        generated_utc="2026-07-05T00:00:00Z",
    )

    paths = write_report(report, tmp_path / "out")

    assert Path(paths["json_path"]).is_file()
    assert Path(paths["markdown_path"]).is_file()
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    assert "kalshi-prior-only-donor-gate" in makefile
    assert "scripts/kalshi_prior_only_donor_gate.py" in makefile
