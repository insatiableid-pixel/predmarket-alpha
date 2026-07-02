#!/usr/bin/env python3
"""Record CI build performance metrics.

Collects job-level timing data from the current CI run and writes it as a
JSON artifact for trend analysis. Runs at the end of the CI pipeline to
capture actual wall-clock durations.

In CI, this is invoked with environment variables set by GitHub Actions:
    BUILD_METRICS_FILE, GITHUB_RUN_ID, GITHUB_SHA

Usage:
    python3 scripts/record_build_metrics.py --output .tmp/build-metrics.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", "-o", default=".tmp/build-metrics.json")
    ap.add_argument("--job-name", default=os.getenv("GITHUB_JOB", "unknown"))
    ap.add_argument("--duration-seconds", type=float, default=None,
                    help="Explicit duration; if omitted, uses BUILD_DURATION env var")
    args = ap.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    duration = args.duration_seconds
    if duration is None:
        env_dur = os.getenv("BUILD_DURATION", "")
        try:
            duration = float(env_dur) if env_dur else None
        except ValueError:
            duration = None

    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "run_id": os.getenv("GITHUB_RUN_ID", "local"),
        "sha": os.getenv("GITHUB_SHA", "unknown")[:12],
        "job": args.job_name,
        "duration_seconds": round(duration, 1) if duration else None,
        "python_version": os.getenv("PYTHON_VERSION", f"{sys.version_info.major}.{sys.version_info.minor}"),
        "cache_hit": os.getenv("CACHE_HIT", "unknown"),
    }

    # Append to history file for local trend tracking
    history_path = ROOT / ".tmp" / "build-metrics-history.jsonl"
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    output_path.write_text(json.dumps(entry, indent=2), encoding="utf-8")
    print(f"Build metrics: job={entry['job']} duration={entry['duration_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
