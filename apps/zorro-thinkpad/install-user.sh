#!/usr/bin/env bash
# ThinkPad app: user part (no sudo). Safe to rerun. keyd is started by Openbox autostart.
set -euo pipefail
here=$(dirname "$(realpath "$0")")
mkdir -p ~/.local/bin ~/.local/share/applications
ln -sfn "$here/zorro-thinkpad" ~/.local/bin/zorro-thinkpad
ln -sfn "$here/zorro-thinkpad.desktop" ~/.local/share/applications/zorro-thinkpad.desktop
echo "zorro-thinkpad linked (rofi: ThinkPad)"
