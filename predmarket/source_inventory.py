"""Donor repository inventory for the Kalshi EV engine.

The inventory is intentionally descriptive.  Donor repositories are never
imported as runtime dependencies; their outputs enter predmarket-alpha only as
validated research artifacts.
"""

from __future__ import annotations

import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from predmarket.shared_helpers import utc_now


@dataclass(frozen=True, slots=True)
class SourceRepoDescriptor:
    repo_id: str
    path: str
    donor_type: str
    admission_status: str
    family_ids: tuple[str, ...] = ()
    admissible_artifacts: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True, slots=True)
class SourceRepoSnapshot:
    descriptor: SourceRepoDescriptor
    exists: bool
    git_branch: str | None
    git_dirty_count: int
    git_untracked_count: int
    artifact_count: int
    existing_artifact_count: int

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row.update(asdict(self.descriptor))
        row.pop("descriptor", None)
        return row


DEFAULT_SOURCE_REPOS: tuple[SourceRepoDescriptor, ...] = (
    SourceRepoDescriptor(
        repo_id="mlb-platform",
        path="/home/mrwatson/projects/mlb-platform",
        donor_type="model-output",
        admission_status="admit_via_external_artifact_bridge",
        family_ids=("sports_baseball",),
        admissible_artifacts=(
            "/home/mrwatson/manual_drops/mlb_platform_signal_features/mlb_platform_sports_model_latest.json",
            "/home/mrwatson/projects/mlb-platform/docs/codex/artifacts/type2-betexplorer-market-closing-comparison-latest/type2-betexplorer-market-closing-comparison.json",
            "/home/mrwatson/projects/mlb-platform/docs/codex/artifacts/type2-settled-outcome-validation-latest/type2-settled-outcome-validation.json",
        ),
        blockers=("current evidence does not support threshold/policy change",),
        notes="Use model/evidence artifacts only; do not import repo code.",
    ),
    SourceRepoDescriptor(
        repo_id="nfl_quant_glm51_greenfield",
        path="/home/mrwatson/projects/nfl_quant_glm51_greenfield",
        donor_type="model-output",
        admission_status="admit_via_external_artifact_bridge",
        family_ids=("sports_football",),
        admissible_artifacts=(
            "/home/mrwatson/manual_drops/kalshi_ev_contract_mappings/kalshi_ev_nfl_contract_mapping_overlay_keys_96008378d65c.json",
            "/home/mrwatson/manual_drops/kalshi_ev_probabilities/kalshi_ev_nfl_calibrated_probability_overlay_keys_96008378d65c.json",
            "/home/mrwatson/projects/nfl_quant_glm51_greenfield/docs/codex/artifacts/nfl-line-readiness-latest/fair-line-review.json",
            "/home/mrwatson/projects/nfl_quant_glm51_greenfield/docs/codex/artifacts/nfl-historical-line-backtest-latest/historical-line-backtest.json",
            "/home/mrwatson/projects/nfl_quant_glm51_greenfield/docs/codex/artifacts/nfl-calibration-overlay-latest/calibration-overlay.json",
        ),
        blockers=("forward context not yet due for the 2026 season",),
        notes="Existing EV ledger overlays are the fastest paper-engine surface.",
    ),
    SourceRepoDescriptor(
        repo_id="atp-oracle",
        path="/home/mrwatson/projects/atp-oracle",
        donor_type="model-output",
        admission_status="watch_only_until_oos_labels",
        family_ids=("sports_tennis",),
        admissible_artifacts=(
            "/home/mrwatson/projects/atp-oracle/docs/codex/artifacts/kalshi-forward-oos-latest/report.json",
            "/home/mrwatson/projects/atp-oracle/docs/codex/artifacts/kalshi-forward-oos-liquidity-latest/liquidity.json",
            "/home/mrwatson/projects/atp-oracle/docs/codex/artifacts/kalshi-bettable-line-gate-latest/bettable-line-gate.json",
            "/home/mrwatson/projects/atp-oracle/docs/codex/artifacts/kalshi-forward-oos-price-observations-latest/prices.json",
            "/home/mrwatson/projects/atp-oracle/data/kalshi/matches-2026-07-03.json",
        ),
        blockers=(
            "needs predmarket settlement labels plus passing ATP forward-OOS, liquidity, and bettable-line gates",
        ),
    ),
    SourceRepoDescriptor(
        repo_id="nba-analytics-platform",
        path="/home/mrwatson/projects/nba-analytics-platform",
        donor_type="hold",
        admission_status="blocked_market_benchmark",
        family_ids=("sports_basketball",),
        admissible_artifacts=(
            "/home/mrwatson/projects/nba-analytics-platform/docs/codex/artifacts/nba-market-claim-gate-latest/nba-market-claim-gate.json",
        ),
        blockers=("no non-market challenger currently beats the market benchmark",),
    ),
    SourceRepoDescriptor(
        repo_id="us-statarb-lab",
        path="/home/mrwatson/projects/us-statarb-lab",
        donor_type="source-data",
        admission_status="admit_public_source_adapters",
        family_ids=("macro_rates", "corporate_edgar", "commodities_energy"),
        admissible_artifacts=(
            "/home/mrwatson/projects/us-statarb-lab/data/curated/platform_readiness/date=2026-04-28/public_snapshot_adapter_audit.csv",
            "/home/mrwatson/projects/us-statarb-lab/data/curated/platform_readiness/date=2026-04-28/daily_gate_summary.json",
        ),
        notes="Import public-source feature contracts, not securities backtest alpha.",
    ),
    SourceRepoDescriptor(
        repo_id="odds-surveillance-platform",
        path="/home/mrwatson/projects/odds-surveillance-platform",
        donor_type="evidence-control",
        admission_status="admit_patterns_only",
        family_ids=("cross_market_surveillance",),
        blockers=("avoid arb-swarm/live paths",),
        notes="Use source manifest, mapping, fee/liquidity, and negative-control patterns.",
    ),
    SourceRepoDescriptor(
        repo_id="numeraire",
        path="/home/mrwatson/projects/numeraire",
        donor_type="math-control",
        admission_status="admit_small_primitives_only",
        family_ids=("signal_formula", "calibration", "paper_sizing"),
        blockers=("dirty/untracked donor state; never import as runtime dependency",),
        notes="Adapt safe formula DSL, calibration metrics, and later Kelly math.",
    ),
    SourceRepoDescriptor(
        repo_id="speculator_ev_engine",
        path="/home/mrwatson/projects/speculator_ev_engine",
        donor_type="math-control",
        admission_status="hold_until_sizing_gate",
        family_ids=("paper_sizing",),
        blockers=("sizing remains gated behind falsification/capacity/correlation/decay",),
    ),
)


def build_source_repo_inventory(
    descriptors: tuple[SourceRepoDescriptor, ...] = DEFAULT_SOURCE_REPOS,
    *,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    snapshots = [snapshot_source_repo(descriptor) for descriptor in descriptors]
    status_counts = Counter(snapshot.descriptor.admission_status for snapshot in snapshots)
    donor_type_counts = Counter(snapshot.descriptor.donor_type for snapshot in snapshots)
    dirty_count = sum(1 for snapshot in snapshots if snapshot.git_dirty_count > 0)
    return {
        "schema_version": 1,
        "generated_utc": generated_utc or utc_now(),
        "status": "source_repo_inventory_ready",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "summary": {
            "repo_count": len(snapshots),
            "existing_repo_count": sum(1 for snapshot in snapshots if snapshot.exists),
            "dirty_repo_count": dirty_count,
            "artifact_count": sum(snapshot.artifact_count for snapshot in snapshots),
            "existing_artifact_count": sum(
                snapshot.existing_artifact_count for snapshot in snapshots
            ),
            "admission_status_counts": dict(sorted(status_counts.items())),
            "donor_type_counts": dict(sorted(donor_type_counts.items())),
        },
        "repos": [snapshot.to_row() for snapshot in snapshots],
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "runtime_dependency_imports_from_donor_repos": False,
        },
    }


def snapshot_source_repo(descriptor: SourceRepoDescriptor) -> SourceRepoSnapshot:
    repo_path = Path(descriptor.path)
    branch, dirty, untracked = git_state(repo_path)
    artifact_paths = [Path(path) for path in descriptor.admissible_artifacts]
    return SourceRepoSnapshot(
        descriptor=descriptor,
        exists=repo_path.exists(),
        git_branch=branch,
        git_dirty_count=dirty,
        git_untracked_count=untracked,
        artifact_count=len(artifact_paths),
        existing_artifact_count=sum(1 for path in artifact_paths if path.exists()),
    )


def git_state(path: Path) -> tuple[str | None, int, int]:
    if not path.exists():
        return None, 0, 0
    try:
        output = subprocess.run(
            ["git", "status", "--short", "--branch"],
            cwd=path,
            check=False,
            text=True,
            capture_output=True,
            timeout=5,
        ).stdout.splitlines()
    except (OSError, subprocess.TimeoutExpired):
        return None, 0, 0
    branch = output[0].removeprefix("## ").strip() if output else None
    dirty_lines = [line for line in output[1:] if line.strip() and not line.startswith("??")]
    untracked_lines = [line for line in output[1:] if line.startswith("??")]
    return branch, len(dirty_lines), len(untracked_lines)
