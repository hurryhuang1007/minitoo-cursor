#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS="$ROOT/divoom-minitoo-osx/tools"
BIN="$TOOLS/minitoo-supervisor"
MAC="${1:-B1:21:81:91:DE:0A}"
LABEL="com.hurry.minitoo-supervisor"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOGDIR="$HOME/.minitoo"

mkdir -p "$LOGDIR" "$HOME/Library/LaunchAgents"

echo "Building supervisor..."
/usr/bin/swiftc \
  "$ROOT/supervisor/MiniTooSupervisor.swift" \
  -framework Foundation \
  -framework IOBluetooth \
  -O \
  -o "$BIN"
chmod 755 "$BIN"

# Stop old agent and any leftover children from previous runs
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl unload "$PLIST" 2>/dev/null || true
pkill -f 'minitoo-supervisor' 2>/dev/null || true
pkill -f 'cursor_minitoo_bridge.py' 2>/dev/null || true
pkill -f "divoom-daemon ${MAC}" 2>/dev/null || true
sleep 1

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${BIN}</string>
    <string>${ROOT}</string>
    <string>${MAC}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>StandardOutPath</key>
  <string>${LOGDIR}/supervisor.launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOGDIR}/supervisor.launchd.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin</string>
  </dict>
</dict>
</plist>
EOF

launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl kickstart -k "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl start "$LABEL"

sleep 1
echo "Installed LaunchAgent: $PLIST"
echo "Supervisor binary: $BIN"
launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | head -30 || true
echo "Logs: $LOGDIR/supervisor.log"
