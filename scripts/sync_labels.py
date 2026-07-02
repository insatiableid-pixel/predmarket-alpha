#!/usr/bin/env python3
"""Sync GitHub issue labels from .github/labels.yml.

Usage:
    python3 scripts/sync_labels.py          # dry-run (print planned changes)
    python3 scripts/sync_labels.py --apply  # create/update labels via gh CLI

Creates priority (P0-P3), type, and area labels to enable programmatic
issue triage and filtering for autonomous agents.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LABELS_PATH = ROOT / ".github" / "labels.yml"


def load_labels() -> list[dict]:
    with open(LABELS_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, list) else []


def existing_labels() -> dict[str, dict]:
    result = subprocess.run(
        ["gh", "label", "list", "--json", "name,color,description", "--limit", "100"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if result.returncode != 0:
        return {}
    labels = json.loads(result.stdout) if result.stdout.strip() else []
    return {lbl["name"]: lbl for lbl in labels}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="create/update labels (default: dry-run)")
    args = ap.parse_args()

    desired = load_labels()
    current = existing_labels()

    created = 0
    updated = 0
    for label in desired:
        name = label["name"]
        color = label.get("color", "ededed")
        desc = label.get("description", "")
        existing = current.get(name)
        needs_update = (
            existing is None
            or existing.get("color") != color
            or existing.get("description") != desc
        )
        if not needs_update:
            continue
        if existing is None:
            action = "CREATE"
        else:
            action = "UPDATE"
        print(f"  {action:7} {name:20} color={color} desc={desc}")
        if args.apply:
            cmd = ["gh", "label", "create" if existing is None else "edit", name]
            if existing is not None:
                cmd.append("--force")
            cmd.extend(["--color", color, "--description", desc])
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
            if result.returncode != 0:
                print(f"    ERROR: {result.stderr.strip()}", file=sys.stderr)
            else:
                created += 1 if existing is None else 0
                updated += 1 if existing is not None else 0

    if not args.apply:
        print(f"\nDry run: {len(desired)} labels defined, {len(current)} exist on GitHub.")
        print("Run with --apply to create/update.")
    else:
        print(f"\nDone: {created} created, {updated} updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
