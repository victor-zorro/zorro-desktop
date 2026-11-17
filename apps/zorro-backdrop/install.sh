#!/usr/bin/env bash
# Install the moving desktop background for the current user (no sudo). Safe to rerun.
# Openbox autostart starts it. Needs python3-gi, python3-gi-cairo, gir1.2-gtk-3.0.
set -euo pipefail
here=$(dirname "$(realpath "$0")")
mkdir -p ~/.local/bin
ln -sfn "$here/zorro-backdrop" ~/.local/bin/zorro-backdrop
echo "zorro-backdrop linked (starts with the Openbox session)"
