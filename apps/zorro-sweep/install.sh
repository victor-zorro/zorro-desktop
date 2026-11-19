#!/usr/bin/env bash
# Install Sweep notes for the current user (no sudo). Safe to rerun.
# Needs: python3-gi, python3-gi-cairo, gir1.2-gtk-3.0; python3-numpy and the zorro-search
# index for the "best match" (works without, just no suggestion).
set -euo pipefail
here=$(dirname "$(realpath "$0")")
mkdir -p ~/.local/bin ~/.local/share/applications
ln -sfn "$here/zorro-sweep" ~/.local/bin/zorro-sweep
ln -sfn "$here/zorro-sweep.desktop" ~/.local/share/applications/zorro-sweep.desktop
echo "Sweep notes installed (Dialer / rofi: Sweep notes)"
