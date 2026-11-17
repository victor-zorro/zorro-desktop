#!/usr/bin/env bash
# Install the living wallpaper for the current user (no sudo). Safe to rerun.
# Openbox autostart starts it. Needs gir1.2-webkit2-4.1 (also used by zorro-dm).
set -euo pipefail
here=$(dirname "$(realpath "$0")")
mkdir -p ~/.local/bin
ln -sfn "$here/zorro-wall" ~/.local/bin/zorro-wall
echo "zorro-wall linked (settings: Zorro → Desktop → Wallpaper)"
