#!/bin/bash
set -e

echo "Installing AIBar..."

# Collector script
mkdir -p ~/.local/bin
cp collector/aibar-collector.py ~/.local/bin/
chmod +x ~/.local/bin/aibar-collector.py
echo "  Installed collector to ~/.local/bin/aibar-collector.py"

# Systemd timer
mkdir -p ~/.config/systemd/user
cp systemd/aibar-collector.service ~/.config/systemd/user/
cp systemd/aibar-collector.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now aibar-collector.timer
echo "  Installed and started systemd timer"

# Create cache directory
mkdir -p ~/.cache/aibar
echo "  Created cache directory"

# Run collector once to populate initial data
~/.local/bin/aibar-collector.py > /dev/null 2>&1 || true
echo "  Ran initial data collection"

echo ""
echo "Done! Collector is running every 30 seconds."
echo ""
echo "To install Quickshell modules, copy them to your config:"
echo "  cp quickshell/services/AIBar.qml ~/.config/quickshell/<config>/services/"
echo "  cp quickshell/modules/aibar/*.qml ~/.config/quickshell/<config>/modules/<bar>/aibar/"
echo ""
echo "Then restart Quickshell."
