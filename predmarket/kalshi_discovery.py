"""End-to-end Kalshi discovery runner.

The runner is the bridge between the Kalshi resolved-row dataset and the
agentic discovery lab. It can optionally build/persist fresh resolved rows from
Kalshi public market data, then runs discovery over stored rows and writes a
compact, reviewable report.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from predmarket.config import Config, load_config
from predmarket.discovery import AgenticDiscoveryConfig, AgenticSignalDiscoveryEngine
from predmarket.kalshi_dataset import (
    KalshiResolvedDatasetBuilder,
    build_dataset_from_kalshi_api,
    persist_rows,
)
from predmarket.store import PointInTimeStore


@dataclass
class KalshiDiscoveryRunnerConfig:
    n_trajectories: int = 4
    iterations_per_trajectory: int = 32
    top_k: int = 10
    min_support: int = 20
    random_seed: int = 42
    evolution_interval: int = 8
    backtest_min_train_size: int = 20
    backtest_test_size: int = 10
    backtest_step_size: int = 10
    market_id: Optional[str] = None
    min_as_of_ts: Optional[float] = None
    max_as_of_ts: Optional[float] = None

    def to_discovery_config(self) -> AgenticDiscoveryConfig:
        return AgenticDiscoveryConfig(
            n_trajectories=self.n_trajectories,
            iterations_per_trajectory=self.iterations_per_trajectory,
            top_k=self.top_k,
            random_seed=self.random_seed,
            research_only=True,
            min_support=self.min_support,
            evolution_interval=self.evolution_interval,
            backtest_min_train_size=self.backtest_min_train_size,
            backtest_test_size=self.backtest_test_size,
            backtest_step_size=self.backtest_step_size,
        )


@dataclass
class KalshiDiscoveryArtifacts:
    report: Dict[str, Any]
    json_path: Path
    markdown_path: Path


def load_rows_for_discovery(
    store: PointInTimeStore,
    config: KalshiDiscoveryRunnerConfig,
) -> List[Dict[str, Any]]:
    rows = store.load_kalshi_resolved_rows(
        market_id=config.market_id,
        min_as_of_ts=config.min_as_of_ts,
        max_as_of_ts=config.max_as_of_ts,
    )
    return [row for row in rows if str(row.get("venue", "")).lower() == "kalshi"]


def summarize_rows(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {
            "n_rows": 0,
            "n_markets": 0,
            "n_events": 0,
            "outcome_yes_rate": 0.0,
            "as_of_min": None,
            "as_of_max": None,
            "domains": {},
            "horizons": {},
            "liquidity_buckets": {},
        }

    def counts(field: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for row in rows:
            key = str(row.get(field, "unknown"))
            out[key] = out.get(key, 0) + 1
        return dict(sorted(out.items(), key=lambda item: (-item[1], item[0])))

    as_of_values = [float(row.get("as_of_ts", 0.0)) for row in rows]
    outcomes = [float(row.get("outcome", 0.0)) for row in rows]
    return {
        "n_rows": len(rows),
        "n_markets": len({row.get("market_id") for row in rows}),
        "n_events": len({row.get("event_id") for row in rows}),
        "outcome_yes_rate": sum(outcomes) / len(outcomes) if outcomes else 0.0,
        "as_of_min": min(as_of_values),
        "as_of_max": max(as_of_values),
        "domains": counts("domain"),
        "horizons": counts("horizon"),
        "liquidity_buckets": counts("liquidity_bucket"),
    }


def compact_discovery_report(
    *,
    discovery_report: Any,
    rows: Sequence[Mapping[str, Any]],
    feature_catalog: Sequence[str],
    runner_config: KalshiDiscoveryRunnerConfig,
) -> Dict[str, Any]:
    full = discovery_report.to_dict()
    top = []
    for item in full.get("top_hypotheses", []):
        hyp = item.get("hypothesis", {})
        metrics = item.get("metrics", {})
        promotion = item.get("promotion", {})
        top.append(
            {
                "hypothesis_id": hyp.get("hypothesis_id"),
                "name": hyp.get("name"),
                "expression": hyp.get("expression"),
                "rationale": hyp.get("rationale"),
                "focus": hyp.get("focus"),
                "complexity": hyp.get("complexity"),
                "reward": item.get("reward"),
                "elo": item.get("elo"),
                "promotion_status": promotion.get("status"),
                "promotion_reasons": promotion.get("reasons", []),
                "metrics": {
                    "n": metrics.get("n"),
                    "brier": metrics.get("brier"),
                    "baseline_brier": metrics.get("baseline_brier"),
                    "log_score": metrics.get("log_score"),
                    "baseline_log_score": metrics.get("baseline_log_score"),
                    "ece": metrics.get("ece"),
                    "execution_return": metrics.get("execution_return"),
                    "deflated_sharpe_ratio": metrics.get("deflated_sharpe_ratio"),
                    "pbo": metrics.get("pbo"),
                },
            }
        )
    return {
        "run_id": full.get("run_id"),
        "created_ts": full.get("created_ts"),
        "runner_config": asdict(runner_config),
        "row_summary": summarize_rows(rows),
        "feature_catalog": list(feature_catalog),
        "top_hypotheses": top,
        "robust_hypothesis_ids": full.get("robust_hypothesis_ids", []),
        "queued_proposal_ids": full.get("queued_proposal_ids", []),
        "trajectory_summaries": full.get("trajectory_summaries", []),
        "rejected_contrasts": full.get("rejected_contrasts", []),
        "full_discovery_run_id": full.get("run_id"),
    }


def write_report(
    report: Mapping[str, Any],
    *,
    reports_dir: Path,
) -> KalshiDiscoveryArtifacts:
    reports_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(report.get("run_id") or f"kalshi-discovery-{int(time.time())}")
    json_path = reports_dir / f"{run_id}.json"
    markdown_path = reports_dir / f"{run_id}.md"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True, default=str)
    with markdown_path.open("w", encoding="utf-8") as f:
        f.write(render_markdown_report(report))
    return KalshiDiscoveryArtifacts(dict(report), json_path, markdown_path)


def render_markdown_report(report: Mapping[str, Any]) -> str:
    summary = report.get("row_summary", {})
    lines = [
        f"# Kalshi Discovery Report: {report.get('run_id', '')}",
        "",
        "## Dataset",
        "",
        f"- Rows: {summary.get('n_rows', 0)}",
        f"- Markets: {summary.get('n_markets', 0)}",
        f"- Events: {summary.get('n_events', 0)}",
        f"- YES outcome rate: {float(summary.get('outcome_yes_rate', 0.0)):.2%}",
        f"- Domains: {summary.get('domains', {})}",
        f"- Horizons: {summary.get('horizons', {})}",
        f"- Liquidity buckets: {summary.get('liquidity_buckets', {})}",
        "",
        "## Top Hypotheses",
        "",
    ]
    top = report.get("top_hypotheses", [])
    if not top:
        lines.append("No hypotheses evaluated. Add more resolved Kalshi rows and rerun discovery.")
    for idx, item in enumerate(top, start=1):
        metrics = item.get("metrics", {})
        lines.extend(
            [
                f"### {idx}. {item.get('name', '')}",
                "",
                f"- Expression: `{item.get('expression', '')}`",
                f"- Focus: {item.get('focus', '')}",
                f"- Reward: {float(item.get('reward') or 0.0):.4f}",
                f"- Promotion: {item.get('promotion_status', '')}",
                f"- Promotion reasons: {item.get('promotion_reasons', [])}",
                f"- Brier: {metrics.get('brier')} vs baseline {metrics.get('baseline_brier')}",
                f"- ECE: {metrics.get('ece')}",
                f"- Execution return proxy: {metrics.get('execution_return')}",
                "",
                str(item.get("rationale", "")),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def run_kalshi_discovery(
    store: PointInTimeStore,
    *,
    config: Optional[KalshiDiscoveryRunnerConfig] = None,
    reports_dir: Optional[Path] = None,
) -> KalshiDiscoveryArtifacts:
    config = config or KalshiDiscoveryRunnerConfig()
    rows = load_rows_for_discovery(store, config)
    if not rows:
        raise ValueError("No stored Kalshi resolved rows found. Run predmarket.kalshi_dataset --write first.")
    feature_catalog = KalshiResolvedDatasetBuilder.feature_catalog(rows)
    engine = AgenticSignalDiscoveryEngine(store=store)
    discovery_report = engine.run(
        config.to_discovery_config(),
        rows,
        feature_catalog=feature_catalog,
    )
    report = compact_discovery_report(
        discovery_report=discovery_report,
        rows=rows,
        feature_catalog=feature_catalog,
        runner_config=config,
    )
    out_dir = reports_dir or (store.research_dir / "reports")
    return write_report(report, reports_dir=out_dir)


async def build_rows_if_requested(
    config: Config,
    store: PointInTimeStore,
    *,
    enabled: bool,
    limit: int,
    max_pages: int,
    days_back: int,
    series_ticker: Optional[str],
    period_interval: int,
) -> int:
    if not enabled:
        return 0
    result = await build_dataset_from_kalshi_api(
        config,
        limit=limit,
        max_pages=max_pages,
        days_back=days_back,
        series_ticker=series_ticker,
        period_interval=period_interval,
    )
    persist_rows(store, result.rows)
    return len(result.rows)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Kalshi resolved-row alpha discovery")
    parser.add_argument("--build-from-api", action="store_true", help="Fetch/persist fresh Kalshi settled rows before discovery")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--days-back", type=int, default=180)
    parser.add_argument("--series-ticker", default=None)
    parser.add_argument("--period-interval", type=int, default=1440, choices=[1, 60, 1440])
    parser.add_argument("--market-id", default=None)
    parser.add_argument("--n-trajectories", type=int, default=4)
    parser.add_argument("--iterations", type=int, default=32)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--min-support", type=int, default=20)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--evolution-interval", type=int, default=8)
    parser.add_argument("--backtest-min-train-size", type=int, default=20)
    parser.add_argument("--backtest-test-size", type=int, default=10)
    parser.add_argument("--backtest-step-size", type=int, default=10)
    parser.add_argument("--reports-dir", default=None)
    args = parser.parse_args(argv)

    app_config = load_config()
    store = PointInTimeStore(app_config.global_cfg.data_dir)
    artifacts: Optional[KalshiDiscoveryArtifacts] = None
    built_rows = 0
    try:
        built_rows = asyncio.run(
            build_rows_if_requested(
                app_config,
                store,
                enabled=args.build_from_api,
                limit=args.limit,
                max_pages=args.max_pages,
                days_back=args.days_back,
                series_ticker=args.series_ticker,
                period_interval=args.period_interval,
            )
        )
        runner_config = KalshiDiscoveryRunnerConfig(
            n_trajectories=args.n_trajectories,
            iterations_per_trajectory=args.iterations,
            top_k=args.top_k,
            min_support=args.min_support,
            random_seed=args.random_seed,
            evolution_interval=args.evolution_interval,
            backtest_min_train_size=args.backtest_min_train_size,
            backtest_test_size=args.backtest_test_size,
            backtest_step_size=args.backtest_step_size,
            market_id=args.market_id,
        )
        artifacts = run_kalshi_discovery(
            store,
            config=runner_config,
            reports_dir=Path(args.reports_dir) if args.reports_dir else None,
        )
    finally:
        store.close()

    if artifacts is None:
        raise RuntimeError("Kalshi discovery did not produce report artifacts")
    print(
        json.dumps(
            {
                "built_rows": built_rows,
                "run_id": artifacts.report["run_id"],
                "rows": artifacts.report["row_summary"]["n_rows"],
                "top_hypotheses": len(artifacts.report["top_hypotheses"]),
                "json_path": str(artifacts.json_path),
                "markdown_path": str(artifacts.markdown_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI smoke path
    raise SystemExit(main())
