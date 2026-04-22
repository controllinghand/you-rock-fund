#!/bin/bash
# Double-click this file to run the YRVI pre-flight check in Terminal.
# .command files open in Terminal automatically on macOS — no permissions needed.

PROJ=$(cd "$(dirname "$0")" && pwd)

source "$PROJ/venv/bin/activate"
bash "$PROJ/startup.sh"

echo ""
echo "Press any key to close this window..."
read -n 1 -s
