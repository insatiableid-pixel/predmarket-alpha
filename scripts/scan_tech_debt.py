#!/usr/bin/env python3
"""Scan the source tree for technical-debt markers (TODO/FIXME/HACK/XXX/NOTE).

Reports per-marker counts, per-file counts, and a total. Exits non-zero only
when the total *increases* beyond the recorded baseline so CI can adopt a
ratchet model identical to ``scripts/ruff_baseline_check.py``.

Usage:
    make tech-debt                 # report current markers
    python3 scripts/scan_tech_debt.py --check     # ratchet gate vs baseline
    python3 scripts/scan_tech_debt.py --regen     # rewrite baseline file
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ["predmarket", "scripts", "main.py"]
BASELINE_PATH = ROOT / ".tech-debt-baseline.json"
MARKER_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX|NOTE)\b")


def scan() -> list[dict]:
    findings: list[dict] = []
    for target in TARGETS:
        base = ROOT / target
        if base.is_file() and base.suffix == ".py":
            files = [base]
        else:
            files = sorted(base.rglob("*.py")) if base.is_dir() else []
        for path in files:
            rel = path.relative_to(ROOT).as_posix()
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, start=1):
                if MARKER_RE.search(line):
                    findings.append({"file": rel, "line": lineno, "marker": line.strip()})
    return findings


def summarize(findings: list[dict]) -> dict:
    per_file: dict[str, int] = {}
    per_kind: dict[str, int] = {}
    for f in findings:
        per_file[f["file"]] = per_file.get(f["file"], 0) + 1
        kind = MARKER_RE.search(f["marker"]).group(1)  # type: ignore[union-attr]
        per_kind[kind] = per_kind.get(kind, 0) + 1
    return {"total": len(findings), "per_file": per_file, "per_kind": per_kind}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="ratchet gate against baseline")
    ap.add_argument("--regen", action="store_true", help="rewrite the baseline file")
    args = ap.parse_args()

    findings = scan()
    summary = summarize(findings)

    if args.regen:
        BASELINE_PATH.write_text(json.dumps({"total": summary["total"]}, indent=2) + "\n")
        print(f"Baseline written: {summary['total']} markers -> {BASELINE_PATH.name}")
        return 0

    print(f"Technical-debt markers: {summary['total']} total")
    for kind, n in sorted(summary["per_kind"].items(), key=lambda kv: -kv[1]):
        print(f"  {kind:8} {n}")
    for path, n in sorted(summary["per_file"].items(), key=lambda kv: -kv[1])[:20]:
        print(f"  {n:4}  {path}")

    if args.check:
        if not BASELINE_PATH.exists():
            print(f"NOTE  {BASELINE_PATH.name} missing — run `make tech-debt-regen` first.", file=sys.stderr)
            return 0
        baseline = json.loads(BASELINE_PATH.read_text())["total"]
        if summary["total"] > baseline:
            print(
                f"FAIL  tech-debt markers increased: {summary['total']} > {baseline} baseline "
                f"(+{summary['total'] - baseline} new).",
                file=sys.stderr,
            )
            return 1
        print(f"OK  {summary['total']}/{baseline} (ratchet: may decrease, must not increase).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
