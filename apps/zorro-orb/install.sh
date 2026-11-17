#!/usr/bin/env bash
# Install the round info area for the current user (no sudo). Safe to rerun.
# Openbox autostart starts it instead of conky. Needs python3-gi, python3-gi-cairo, gir1.2-gtk-3.0.
set -euo pipefail
here=$(dirname "$(realpath "$0")")
mkdir -p ~/.local/bin
ln -sfn "$here/zorro-orb" ~/.local/bin/zorro-orb
echo "zorro-orb linked (starts with the Openbox session, settings: Zorro → Desktop → Info circle)"
