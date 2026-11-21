#!/usr/bin/env bash
# Intelligence for the current user (no sudo). Safe to rerun.
# Needs python3 + GTK 3 (python3-gi), and for answers and search the two services:
#   apps/zorro-ai/install.sh      apps/zorro-search/install.sh
set -euo pipefail
here=$(dirname "$(realpath "$0")")
mkdir -p ~/.local/bin ~/.local/share/applications
ln -sfn "$here/zorro-intel" ~/.local/bin/zorro-intel
ln -sfn "$here/zorro-intel.desktop" ~/.local/share/applications/zorro-intel.desktop
echo "Intelligence installed (zorro-intel)"
