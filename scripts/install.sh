#!/usr/bin/env bash
# install.sh — first-time setup for the notebook price monitor on Linux
# Usage: bash scripts/install.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "=== Notebook Price Monitor - Installation ==="
echo "Project dir: $PROJECT_DIR"
cd "$PROJECT_DIR"

# --- Python version check ---
if ! command -v python3.11 &>/dev/null && ! command -v "$PYTHON_BIN" &>/dev/null; then
    echo "ERROR: Python 3.11+ is required but was not found in PATH."
    echo "Install Python 3.11+ and make sure it is available as 'python3' or 'python3.11'."
    exit 1
fi

PYTHON="$(command -v python3.11 2>/dev/null || command -v "$PYTHON_BIN")"
PYTHON_VERSION="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
REQUIRED_MAJOR=3
REQUIRED_MINOR=11

MAJOR="${PYTHON_VERSION%%.*}"
MINOR="${PYTHON_VERSION##*.}"
if [ "$MAJOR" -lt "$REQUIRED_MAJOR" ] || { [ "$MAJOR" -eq "$REQUIRED_MAJOR" ] && [ "$MINOR" -lt "$REQUIRED_MINOR" ]; }; then
    echo "ERROR: Python 3.11+ is required, found $PYTHON_VERSION at $PYTHON"
    echo "Please install Python 3.11+ and retry."
    exit 1
fi

echo "==> Using Python $PYTHON_VERSION ($PYTHON)"

# --- Create virtual environment ---
if [ ! -d "$VENV_DIR" ]; then
    echo "==> Creating virtual environment at $VENV_DIR ..."
    "$PYTHON" -m venv "$VENV_DIR"
else
    echo "==> Virtual environment already exists at $VENV_DIR, skipping creation."
fi

# --- Install dependencies ---
echo "==> Installing dependencies from requirements.txt ..."
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install -r requirements.txt

# --- Create data and logs directories ---
echo "==> Creating data/ and logs/ directories ..."
mkdir -p data logs

# --- Copy config templates if not already present ---
if [ ! -f "config.yaml" ]; then
    echo "==> Copying config.example.yaml -> config.yaml ..."
    cp config.example.yaml config.yaml
else
    echo "==> config.yaml already exists, skipping."
fi

if [ ! -f ".env" ]; then
    echo "==> Copying .env.example -> .env ..."
    cp .env.example .env
else
    echo "==> .env already exists, skipping."
fi

# --- Make monitor.py executable ---
chmod +x monitor.py

echo ""
echo "============================================================"
echo "  DONE — Installation complete!"
echo "============================================================"
echo ""
echo "  Next steps:"
echo "    1. Edit .env — set N8N_WEBHOOK_URL to your n8n webhook"
echo "         nano .env"
echo "    2. Edit config.yaml — set target prices and product SKUs"
echo "         nano config.yaml"
echo "    3. Test the setup (no writes, no real alerts):"
echo "         $VENV_DIR/bin/python monitor.py --dry-run"
echo ""
echo "  To install the cron job (runs at 6:00 and 18:00 daily):"
echo "    bash scripts/install_cron.sh"
echo ""
