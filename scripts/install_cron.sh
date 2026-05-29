#!/usr/bin/env bash
# install_cron.sh — configure crontab to run the price monitor twice daily
# Usage: bash scripts/install_cron.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Resolve absolute paths
APP_DIR="$(realpath "$PROJECT_DIR")"
VENV_PYTHON="$APP_DIR/.venv/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "ERROR: Virtual environment not found at $APP_DIR/.venv"
    echo "Run 'bash scripts/install.sh' first."
    exit 1
fi

CRON_LINE="0 6,18 * * * cd $APP_DIR && $VENV_PYTHON monitor.py >> $APP_DIR/logs/cron.log 2>&1"

echo ""
echo "  The following cron entry will be added:"
echo ""
echo "    $CRON_LINE"
echo ""
read -r -p "Install cron? [y/N] " confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Aborted. No changes made."
    exit 0
fi

# Check for duplicate entry
if crontab -l 2>/dev/null | grep -qF "$APP_DIR && $VENV_PYTHON monitor.py"; then
    echo "Cron entry already exists. No changes made."
    exit 0
fi

# Add the new cron entry (preserve existing crontab)
(crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -

echo ""
echo "Cron job installed. Runs at 6:00 and 18:00 daily."
echo "Logs will be written to: $APP_DIR/logs/cron.log"
echo ""
echo "To verify: crontab -l"
echo "To remove: crontab -e  (then delete the line manually)"
echo ""
