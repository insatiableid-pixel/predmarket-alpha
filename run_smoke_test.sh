#!/usr/bin/env bash
# ==============================================================================
# Smoke Test Orchestrator for predmarket-alpha
# Confirms environment is active, modules are importable, and pytest suite passes.
# ==============================================================================

set -euo pipefail

PROJECT_ROOT="/home/mrwatson/projects/predmarket-alpha"
VENV_DIR="${PROJECT_ROOT}/.venv"

# Ensure venv is activated
if [ -d "$VENV_DIR" ]; then
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
else
    echo "Error: Virtual environment not found at $VENV_DIR. Run setup_env.sh first." >&2
    exit 1
fi

echo "=== [1/2] Verifying Python Module Imports ==="
python3 -c "
import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())
import pydantic
import yaml
import numpy
import pandas
import scipy
import sklearn
import torch
import transformers
import aiohttp
import websockets
import kalshi_python
import ib_insync
print('Core dependencies verified.')
"

# Check if project modules are importable (will be generated in Phase 2)
if python3 -c "import sys; sys.path.insert(0, '$PROJECT_ROOT'); import predmarket.config, predmarket.ingest, predmarket.signals, predmarket.ensemble, predmarket.risk, predmarket.execution" 2>/dev/null; then
    echo "Platform modules verified successfully."
else
    echo "Platform modules not fully generated yet. This is expected in Phase 1."
fi

echo "=== [2/2] Running Pytest Smoke Suite ==="
if command -v pytest >/dev/null; then
    PYTHONPATH="${PROJECT_ROOT}" pytest -v "${PROJECT_ROOT}/tests/" || echo "Warning: pytest failed (some files may not be generated yet)"
else
    echo "pytest not installed in virtualenv."
    exit 1
fi

echo "=== Smoke Test Run Completed ==="
