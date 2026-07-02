#!/usr/bin/env python3
"""Ruff baseline (ratchet) lint+format gate.

Runs ``ruff check`` and ``ruff format --check`` on the full tree, compares
violation counts against ``.ruff-baseline.json``, and fails only when the
count *increases*.  This keeps CI green on legacy codebases while preventing
new violations from slipping in.  As files are cleaned up the baseline is
ratcheted down via ``make lint-baseline-regen``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / ".ruff-baseline.json"
TARGETS = ["predmarket/", "tests/", "main.py"]


def _run_json(cmd: list[str]) -> list:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if result.returncode not in (0, 1):
        print(f"error: {' '.join(cmd)} exited {result.returncode}", file=sys.stderr)
        sys.exit(2)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def lint_error_count() -> int:
    cmd = ["ruff", "check", "--output-format=json", "--exit-zero", *TARGETS]
    return len(_run_json(cmd))


def format_file_count() -> int:
    result = subprocess.run(
        ["ruff", "format", "--check", *TARGETS],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if result.returncode == 0:
        return 0
    count = 0
    for line in result.stdout.splitlines():
        if line.startswith("Would reformat:"):
            count += 1
    return count


def main() -> int:
    baseline = json.loads(BASELINE_PATH.read_text())
    baseline_lint = baseline["lint_error_count"]
    baseline_fmt = baseline["format_file_count"]

    lint = lint_error_count()
    fmt = format_file_count()

    failures: list[str] = []

    if lint > baseline_lint:
        failures.append(
            f"ruff lint violations increased: {lint} > {baseline_lint} baseline "
            f"(+{lint - baseline_lint} new)."
        )
    if fmt > baseline_fmt:
        failures.append(
            f"ruff format files increased: {fmt} > {baseline_fmt} baseline "
            f"(+{fmt - baseline_fmt} new)."
        )

    if failures:
        for msg in failures:
            print(f"FAIL  {msg}", file=sys.stderr)
        print(
            "Fix the new violations or regenerate the baseline with "
            "`make lint-baseline-regen` if the increase is intentional.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK  lint {lint}/{baseline_lint}  format {fmt}/{baseline_fmt}  "
        f"(ratchet: counts may decrease but must not increase)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
