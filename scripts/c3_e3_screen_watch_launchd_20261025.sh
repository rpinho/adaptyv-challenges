#!/bin/bash
# Install a launchd job that pulls the E3 AF2M screen every 2 minutes until 24 are local.
# Self-unloads at 24 scores or at the 00:32 ET hard budget, whichever comes first.
set -euo pipefail
cd "$(dirname "$0")/.."
LABEL=com.ricardo.adaptyv-c3-e3-screen-pull
PLIST=$HOME/Library/LaunchAgents/$LABEL.plist
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$PWD/scripts/c3_e3_pull_screen_20261025.sh</string>
  </array>
  <key>StartInterval</key><integer>120</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$PWD/results/c3_e3_111_20261025/screen_launchd.out</string>
  <key>StandardErrorPath</key><string>$PWD/results/c3_e3_111_20261025/screen_launchd.err</string>
</dict>
</plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load -w "$PLIST"
launchctl list | grep "$LABEL" || echo "NOT LOADED"
