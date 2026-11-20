#!/usr/bin/env bash
# Install Transfer for the current user (no sudo). Safe to rerun.
# Needs: python3-spake2 (packages/common.txt), python3-gi + gir1.2-gtk-3.0.
set -euo pipefail
here=$(dirname "$(realpath "$0")")
mkdir -p ~/.local/bin ~/.local/share/applications ~/Installers
ln -sfn "$here/zorro-transfer" ~/.local/bin/zorro-transfer
ln -sfn "$here/zorro-transfer.desktop" ~/.local/share/applications/zorro-transfer.desktop
python3 -c 'import spake2' 2>/dev/null || echo "Transfer: python3-spake2 is missing (sudo apt install python3-spake2)"
echo "Transfer installed (Dialer: Transfer)"
