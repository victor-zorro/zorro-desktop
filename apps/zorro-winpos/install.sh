#!/usr/bin/env bash
# zorro-winpos for the current user (no sudo). Safe to rerun. Openbox autostart starts it.
# Needs python3-xlib (packages/common.txt).
set -euo pipefail
here=$(dirname "$(realpath "$0")")
mkdir -p ~/.local/bin
ln -sfn "$here/zorro-winpos" ~/.local/bin/zorro-winpos
echo "zorro-winpos linked (windows reopen where you left them)"
