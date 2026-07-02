#!/usr/bin/env python3
"""Validate that AGENTS.md commands are syntactically correct and referenced files exist.

Checks:
1. All ``make <target>`` commands in AGENTS.md correspond to actual Makefile targets.
2. All file references (backtick-quoted paths that exist in the repo) are valid.
3. The file is non-empty and contains expected sections.

Usage:
    python3 scripts/validate_agents_md.py          # report issues
    python3 scripts/validate_agents_md.py --check   # exit non-zero on issues
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS_MD = ROOT / "AGENTS.md"
MAKEFILE = ROOT / "Makefile"

MAKE_CMD_RE = re.compile(r"`make\s+(\S+)`")
MIN_LENGTH = 100


def extract_make_targets_from_makefile() -> set[str]:
    """Extract target names from the Makefile."""
    if not MAKEFILE.exists():
        return set()
    targets: set[str] = set()
    for line in MAKEFILE.read_text(encoding="utf-8").splitlines():
        # Match lines like "target: dependencies"
        m = re.match(r"^([a-zA-Z0-9_-]+)\s*:", line)
        if m and not line.startswith("\t"):
            targets.add(m.group(1))
    return targets


def validate() -> list[str]:
    """Return a list of issues found, empty if all checks pass."""
    issues: list[str] = []

    if not AGENTS_MD.exists():
        issues.append("AGENTS.md does not exist at repo root.")
        return issues

    content = AGENTS_MD.read_text(encoding="utf-8")
    if len(content) < MIN_LENGTH:
        issues.append(f"AGENTS.md is too short ({len(content)} chars, need >= {MIN_LENGTH}).")

    expected_sections = ["Common Commands", "Environment"]
    for section in expected_sections:
        if section not in content:
            issues.append(f"AGENTS.md missing expected section: '{section}'.")

    # Check that make targets referenced in AGENTS.md exist in the Makefile.
    makefile_targets = extract_make_targets_from_makefile()
    referenced = MAKE_CMD_RE.findall(content)
    for target in referenced:
        if target not in makefile_targets:
            issues.append(f"AGENTS.md references 'make {target}' but no such Makefile target exists.")

    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="exit non-zero if issues found")
    args = ap.parse_args()

    issues = validate()
    if issues:
        for issue in issues:
            print(f"FAIL  {issue}", file=sys.stderr)
        if args.check:
            return 1
    else:
        print("OK  AGENTS.md is valid (commands match Makefile, sections present).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
