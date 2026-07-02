#!/usr/bin/env python3
"""Collect code-quality metrics for trend tracking.

Gathers coverage, lint violations, dead-code items, complexity, and
duplicate-code statistics into a single JSON report. Designed to run in CI
and upload as an artifact so quality trends can be monitored over time.

Usage:
    python3 scripts/collect_quality_metrics.py --output .tmp/quality-metrics.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cmd(cmd: list[str]) -> tuple[int, str]:
    """Run a command and return (returncode, combined stdout+stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=120,
        )
        return result.returncode, (result.stdout + result.stderr)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 1, ""


def collect_coverage() -> dict[str, object]:
    """Collect test coverage percentage from a coverage run."""
    # Check if coverage.xml exists from a prior run
    cov_xml = ROOT / "coverage.xml"
    if cov_xml.exists():
        try:
            content = cov_xml.read_text(encoding="utf-8")
            # Parse line-rate from <coverage line-rate="0.85">
            match = re.search(r'line-rate="([0-9.]+)"', content)
            if match:
                rate = float(match.group(1))
                return {"line_rate": round(rate, 4), "line_pct": round(rate * 100, 1)}
        except (OSError, ValueError):
            pass
    return {"line_rate": None, "line_pct": None, "note": "coverage.xml not found"}


def collect_ruff() -> dict[str, object]:
    """Collect ruff lint violation count."""
    rc, output = run_cmd([sys.executable, "-m", "ruff", "check", "predmarket/", "scripts/", "main.py"])
    violations = len(re.findall(r"^[A-Z]\d+", output, re.MULTILINE))
    return {"violations": violations, "exit_code": rc}


def collect_vulture() -> dict[str, object]:
    """Collect dead-code item count from vulture."""
    rc, output = run_cmd([
        sys.executable, "-m", "vulture",
        "predmarket/", "scripts/", "--min-confidence", "60",
    ])
    # Count lines that look like dead-code findings
    items = len([line for line in output.splitlines() if ":" in line and not line.startswith(" ")])
    return {"dead_code_items": items, "exit_code": rc}


def collect_tech_debt() -> dict[str, object]:
    """Collect TODO/FIXME count from the tech-debt baseline."""
    baseline = ROOT / ".tech-debt-baseline.json"
    if baseline.exists():
        try:
            data = json.loads(baseline.read_text(encoding="utf-8"))
            return {"baseline_count": data.get("count", data) if isinstance(data, dict) else data}
        except (json.JSONDecodeError, OSError):
            pass
    # Fallback: count directly
    count = 0
    for py_file in (ROOT / "predmarket").rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            count += len(re.findall(r"\b(TODO|FIXME|HACK|XXX)\b", content))
        except (OSError, UnicodeDecodeError):
            continue
    return {"todo_fixme_count": count}


def collect_feature_flags() -> dict[str, object]:
    """Collect feature flag usage stats."""
    # Count flags by reading the enum definitions directly
    ff_path = ROOT / "predmarket" / "feature_flags.py"
    flag_count = 0
    if ff_path.exists():
        content = ff_path.read_text(encoding="utf-8")
        flag_count = len(re.findall(r"^\s{4}[A-Z][A-Z0-9_]*\s*=\s*[\"'][a-z]", content, re.MULTILINE))

    _rc, output = run_cmd([sys.executable, "scripts/check_feature_flags.py"])
    dead = output.count("FeatureFlag.") if "DEAD FLAGS" in output else 0
    return {
        "total_flags": flag_count,
        "dead_flags": dead,
        "active_flags": flag_count - dead,
    }


def collect_file_sizes() -> dict[str, object]:
    """Collect largest Python source files."""
    sizes = []
    for py_file in (ROOT / "predmarket").rglob("*.py"):
        try:
            lines = len(py_file.read_text(encoding="utf-8").splitlines())
            sizes.append({"file": str(py_file.relative_to(ROOT)), "lines": lines})
        except (OSError, UnicodeDecodeError):
            continue
    for py_file in (ROOT / "scripts").rglob("*.py"):
        try:
            lines = len(py_file.read_text(encoding="utf-8").splitlines())
            sizes.append({"file": str(py_file.relative_to(ROOT)), "lines": lines})
        except (OSError, UnicodeDecodeError):
            continue
    sizes.sort(key=lambda x: x["lines"], reverse=True)
    return {
        "largest_files": sizes[:10],
        "total_files": len(sizes),
        "total_lines": sum(s["lines"] for s in sizes),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", "-o", default=".tmp/quality-metrics.json", help="Output JSON path")
    args = ap.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("Collecting quality metrics...", file=sys.stderr)
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "repository": "predmarket-alpha",
        "metrics": {
            "coverage": collect_coverage(),
            "lint": collect_ruff(),
            "dead_code": collect_vulture(),
            "tech_debt": collect_tech_debt(),
            "feature_flags": collect_feature_flags(),
            "file_sizes": collect_file_sizes(),
        },
    }

    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Quality metrics written to {output_path}", file=sys.stderr)
    print(json.dumps(report["metrics"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
