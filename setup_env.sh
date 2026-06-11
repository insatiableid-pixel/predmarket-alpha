#!/usr/bin/env bash
# ==============================================================================
# Setup Environment Script for predmarket-alpha
# Creates directories, initializes python venv, and installs dependencies.
# ==============================================================================

set -euo pipefail

PROJECT_ROOT="/home/mrwatson/projects/predmarket-alpha"
VENV_DIR="${PROJECT_ROOT}/.venv"

echo "=== [1/4] Creating Directory Structure ==="
mkdir -p "${PROJECT_ROOT}/config"
mkdir -p "${PROJECT_ROOT}/data/raw"
mkdir -p "${PROJECT_ROOT}/data/processed"
mkdir -p "${PROJECT_ROOT}/predmarket"
mkdir -p "${PROJECT_ROOT}/tests"

echo "Directories created successfully."

echo "=== [2/4] Setting Up Python Virtual Environment ==="
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists."
fi

# Activate virtualenv
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

echo "Upgrading pip, setuptools, and wheel..."
pip install --upgrade pip setuptools wheel

echo "=== [3/4] Installing Dependencies ==="
pip install -r "${PROJECT_ROOT}/requirements.txt"

echo "=== [4/4] Configuring Environment Files ==="
if [ ! -f "${PROJECT_ROOT}/.env" ]; then
    echo "Copying .env.template to .env..."
    cp "${PROJECT_ROOT}/.env.template" "${PROJECT_ROOT}/.env"
    echo "Warning: Remember to update credentials in .env before running live."
else
    echo ".env file already exists. Skipping copy."
fi

echo "=== Setup Complete ==="
echo "To activate the environment, run: source ${VENV_DIR}/bin/activate"
