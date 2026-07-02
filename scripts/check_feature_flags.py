#!/usr/bin/env python3
"""Detect stale/dead feature flags by comparing definitions to codebase usage.

Scans for every ``FeatureFlag`` enum member and checks whether it is referenced
anywhere in the codebase outside of ``feature_flags.py`` itself. Flags with zero
external references are reported as potentially dead.

A flag is considered "used" if its enum attribute name (e.g.
``CRYPTO_PROXY_DECAY_MONITORING``) or its string value (e.g.
``crypto_proxy_decay_monitoring``) appears in a ``.py`` file other than
``feature_flags.py`` and its corresponding test file.

Exit codes:
  0  No dead flags found (or --check mode with acceptable count)
  1  Dead flags detected (when run with --check)

Usage:
    python3 scripts/check_feature_flags.py          # report dead flags
    python3 scripts/check_feature_flags.py --check   # exit non-zero on dead flags
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEATURE_FLAGS_FILE = ROOT / "predmarket" / "feature_flags.py"


def extract_flags() -> list[tuple[str, str]]:
    """Extract (enum_name, string_value) pairs from the FeatureFlag enum.

    Returns:
        List of (attribute_name, value) tuples, e.g.
        [("CRYPTO_PROXY_DECAY_MONITORING", "crypto_proxy_decay_monitoring"), ...]
    """
    if not FEATURE_FLAGS_FILE.exists():
        return []

    content = FEATURE_FLAGS_FILE.read_text(encoding="utf-8")
    # Match lines like:  CRYPTO_PROXY_DECAY_MONITORING = "crypto_proxy_decay_monitoring"
    pattern = re.compile(
        r"^\s{4}([A-Z][A-Z0-9_]*)\s*=\s*[\"']([a-z0-9_]+)[\"']",
        re.MULTILINE,
    )
    return pattern.findall(content)


def scan_usage(
    enum_name: str, string_value: str, search_dirs: list[Path]
) -> list[Path]:
    """Check whether a flag is referenced in the codebase.

    Searches for either the enum attribute name or the string value in .py
    files, excluding feature_flags.py and its direct test file.

    Returns:
        List of files that reference the flag (empty if dead).
    """
    referencing_files: list[Path] = []
    skip_files = {
        FEATURE_FLAGS_FILE,
        ROOT / "tests" / "test_config.py",
    }

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for py_file in search_dir.rglob("*.py"):
            py_file = py_file.resolve()
            if py_file in skip_files:
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            # Check for enum attribute reference (e.g. FeatureFlag.CRYPTO_PROXY_...)
            # or the bare string value used with is_enabled()
            if enum_name in content or string_value in content:
                # Avoid false positives: skip if only the enum definition matches
                # a substring of another flag name
                if f"FeatureFlag.{enum_name}" in content:
                    referencing_files.append(py_file)
                elif f'"{string_value}"' in content or f"'{string_value}'" in content:
                    referencing_files.append(py_file)
                elif f"FEATURE_{enum_name}" in content:
                    referencing_files.append(py_file)

    return referencing_files


def check_flags() -> list[dict[str, object]]:
    """Check all flags and return dead flag details.

    Returns:
        List of dicts with keys: name, value. Empty if all flags are used.
    """
    flags = extract_flags()
    if not flags:
        print("WARNING: No FeatureFlag members found in feature_flags.py")
        return []

    search_dirs = [ROOT / "predmarket", ROOT / "scripts", ROOT / "tests"]
    # Handle main.py as a single file
    py_files_at_root = [f for f in [ROOT / "main.py"] if f.exists()]

    dead_flags: list[dict[str, object]] = []
    for enum_name, string_value in flags:
        all_search = [*search_dirs, *py_files_at_root]
        refs = scan_usage(enum_name, string_value, all_search)
        if not refs:
            dead_flags.append({"name": enum_name, "value": string_value})

    return dead_flags


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if dead flags are found",
    )
    args = ap.parse_args()

    dead = check_flags()
    total = len(extract_flags())

    if not dead:
        print(f"OK  All {total} feature flags are referenced in the codebase.")
        return 0

    print(f"DEAD FLAGS: {len(dead)} of {total} flags have no external references:")
    for flag in dead:
        print(f"  - FeatureFlag.{flag['name']}  (value: \"{flag['value']}\")")
    print()
    print("These flags are defined but never used outside feature_flags.py.")
    print("Either remove them or add code paths that reference them.")

    if args.check:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
