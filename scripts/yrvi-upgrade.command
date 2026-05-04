#!/bin/bash
# yrvi-upgrade.command — double-clickable YRVI upgrade script
# Launched automatically by macOS Terminal via the yrvi://upgrade URL scheme.

# cd to repo root (one level up from scripts/ where this file lives)
cd "$(dirname "$0")/.."

echo "================================================"
echo "  YRVI Upgrade — pulling latest code..."
echo "================================================"
echo ""

git pull origin main
if [ $? -ne 0 ]; then
    echo ""
    echo "Upgrade failed — see error above"
    read -rp $'\nPress Enter to close...'
    exit 1
fi

echo ""
echo "Build and restart starting..."
echo ""

bash scripts/yrvi-build.sh all --paper

echo ""
echo "================================================"
echo "  Upgrade complete! Dashboard will reload."
echo "================================================"
echo ""
read -rp $'\nPress Enter to close...'
