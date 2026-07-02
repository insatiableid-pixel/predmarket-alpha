#!/usr/bin/env python3
"""Guard against oversized source files.

Flags Python source files that exceed either a line-count or byte threshold.
The line threshold (default 1500) catches monolithic modules such as the legacy
``scripts/codex_macro_router.py`` (6600+ lines); the byte threshold (default
150 KiB) catches accidental data/log dumps mislabeled as source. Exits non-zero
when any *new* offending file appears, but tolerates the known offenders recorded
in ``.large-file-baseline.json`` so the gate can be adopted on a legacy tree.

Usage:
    make file-sizes                 # report current oversized files
    python3 scripts/check_file_sizes.py --check    # ratchet gate
    python3 scripts/check_file_sizes.py --regen    # rewrite baseline
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ["predmarket", "scripts", "main.py"]
BASELINE_PATH = ROOT / ".large-file-baseline.json"
MAX_LINES = 1500
MAX_BYTES = 150_000


def oversized() -> list[dict]:
    out: list[dict] = []
    for target in TARGETS:
        base = ROOT / target
        files = [base] if base.is_file() else sorted(base.rglob("*.py")) if base.is_dir() else []
        for path in files:
            if path.suffix != ".py":
                continue
            rel = path.relative_to(ROOT).as_posix()
            try:
                size = path.stat().st_size
                lines = sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if lines > MAX_LINES or size > MAX_BYTES:
                out.append({"file": rel, "lines": lines, "bytes": size})
    return sorted(out, key=lambda d: d["lines"], reverse=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="ratchet gate against baseline")
    ap.add_argument("--regen", action="store_true", help="rewrite the baseline file")
    ap.add_argument("--max-lines", type=int, default=MAX_LINES)
    ap.add_argument("--max-bytes", type=int, default=MAX_BYTES)
    args = ap.parse_args()

    found = oversized()
    files = [f["file"] for f in found]

    print(f"Oversized source files (> {args.max_lines} lines or > {args.max_bytes} bytes): {len(found)}")
    for f in found:
        print(f"  {f['lines']:6} lines  {f['bytes']:>9} bytes  {f['file']}")

    if args.regen:
        BASELINE_PATH.write_text(json.dumps({"files": files}, indent=2) + "\n")
        print(f"Baseline written: {len(files)} files -> {BASELINE_PATH.name}")
        return 0

    if args.check:
        if not BASELINE_PATH.exists():
            print(f"NOTE  {BASELINE_PATH.name} missing — run `make file-sizes-regen` first.", file=sys.stderr)
            return 0
        known = set(json.loads(BASELINE_PATH.read_text())["files"])
        new_offenders = [f for f in files if f not in known]
        if new_offenders:
            print("FAIL  new oversized files introduced:", file=sys.stderr)
            for f in new_offenders:
                print(f"       {f}", file=sys.stderr)
            print("Refactor or run `make file-sizes-regen` if the increase is intentional.", file=sys.stderr)
            return 1
        print("OK  no new oversized files (known offenders recorded in baseline).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
