#!/usr/bin/env bash
# Zorro app + ThinkPad keys: user part (no sudo). Safe to rerun. keyd starts from Openbox autostart.
set -euo pipefail
here=$(dirname "$(realpath "$0")")
mkdir -p ~/.local/bin ~/.local/share/applications
ln -sfn "$here/zorro-thinkpad" ~/.local/bin/zorro-thinkpad
ln -sfn "$here/zorro-thinkpad" ~/.local/bin/zorro-settings      # the app: no arguments
rm -f ~/.local/share/applications/zorro-thinkpad.desktop         # old name
ln -sfn "$here/zorro-settings.desktop" ~/.local/share/applications/zorro-settings.desktop
echo "zorro-thinkpad linked (rofi: Zorro)"
