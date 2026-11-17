#!/usr/bin/env bash
# Install the screenshot overlay for the current user (no sudo). Safe to rerun.
# Needs: maim, xclip, x11-utils (xprop/xwininfo), python3-gi, python3-gi-cairo, gir1.2-gtk-3.0.
set -euo pipefail
here=$(dirname "$(realpath "$0")")
mkdir -p ~/.local/bin ~/.local/share/applications
ln -sfn "$here/zorro-shot" ~/.local/bin/zorro-shot
ln -sfn "$here/zorro-shot.desktop" ~/.local/share/applications/zorro-shot.desktop
echo "Screenshot overlay installed (PrtSc, rofi: Screenshot)"
