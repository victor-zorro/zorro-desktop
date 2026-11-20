#!/usr/bin/env bash
# Penpot: the design app in its own Firefox window (zwebapp, class Penpot), on design.penpot.app.
# Your files live in your Penpot account in the cloud. No password needed. Safe to rerun.
set -euo pipefail
mkdir -p ~/.local/share/applications
cat > ~/.local/share/applications/penpot.desktop <<DESK
[Desktop Entry]
Type=Application
Name=Penpot
Comment=Design and prototyping (Penpot in its own window)
Exec=sh -c '\$HOME/.local/bin/zwebapp Penpot penpot https://design.penpot.app'
Icon=zorro-penpot
StartupWMClass=Penpot
Categories=Graphics;VectorGraphics;
DESK
echo "==> Penpot added: find it in the Dialer, sign in once"
