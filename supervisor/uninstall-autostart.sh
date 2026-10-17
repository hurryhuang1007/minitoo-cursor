#!/bin/zsh
set -euo pipefail

LABEL="com.hurry.minitoo-supervisor"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"

# Stop managed children
pkill -f 'cursor_minitoo_bridge.py' 2>/dev/null || true
pkill -f 'divoom-daemon B1:21:81:91:DE:0A' 2>/dev/null || true
pkill -f 'minitoo-supervisor' 2>/dev/null || true

echo "Removed LaunchAgent $LABEL"
