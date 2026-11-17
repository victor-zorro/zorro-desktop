#!/usr/bin/env bash
# Install the dial launcher for the current user (no sudo). Safe to rerun.
# Super+Space (and a Super tap, with xcape) opens it; rofi stays on Super+Shift+Space.
set -euo pipefail
here=$(dirname "$(realpath "$0")")
mkdir -p ~/.local/bin
ln -sfn "$here/zorro-dial" ~/.local/bin/zorro-dial
echo "zorro-dial linked (Super / Super+Space; settings: Zorro → Desktop → Launcher)"
