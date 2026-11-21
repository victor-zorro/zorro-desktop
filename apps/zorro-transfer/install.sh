#!/usr/bin/env bash
# Install Transfer for the current user (no sudo). Safe to rerun.
# Needs: python3-spake2 (packages/common.txt), python3-gi + gir1.2-gtk-3.0.
# The beacon (zorro-beacon.service) lets other devices find this one.
set -euo pipefail
here=$(dirname "$(realpath "$0")")
mkdir -p ~/.local/bin ~/.local/share/applications ~/.config/systemd/user ~/Installers
ln -sfn "$here/zorro-transfer" ~/.local/bin/zorro-transfer
ln -sfn "$here/zorro-transfer.desktop" ~/.local/share/applications/zorro-transfer.desktop
ln -sfn "$here/zorro-beacon.service" ~/.config/systemd/user/zorro-beacon.service
if systemctl --user daemon-reload 2>/dev/null; then
  systemctl --user enable zorro-beacon.service >/dev/null 2>&1 || true
  systemctl --user restart zorro-beacon.service || echo "Transfer: the beacon did not start (journalctl --user -u zorro-beacon)"
else
  echo "Transfer: no user systemd here; run this again after logging in"
fi
python3 -c 'import spake2' 2>/dev/null || echo "Transfer: python3-spake2 is missing (sudo apt install python3-spake2)"
echo "Transfer installed (Dialer: Transfer; this device shows up nearby as $(hostname))"
