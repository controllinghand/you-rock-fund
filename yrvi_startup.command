#!/bin/bash
cd ~/you_rock_fund
bash startup.sh

echo ''
echo 'Press any key to close...'
python3 -c "
import sys, tty, termios
fd = sys.stdin.fileno()
old = termios.tcgetattr(fd)
try:
    tty.setraw(fd)
    sys.stdin.read(1)
finally:
    termios.tcsetattr(fd, termios.TCSADRAIN, old)
"
osascript -e 'tell application "Terminal" to close (every window whose name contains "YRVI")' 2>/dev/null || exit 0
