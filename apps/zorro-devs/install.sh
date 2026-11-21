#!/usr/bin/env bash
# DEVS for the current user (no sudo). Safe to rerun.
# Links the launcher, installs and starts the user service, fills the catalogue
# from the repo (items that are already there are left alone).
set -euo pipefail
here=$(dirname "$(realpath "$0")")
mkdir -p ~/.local/bin ~/.local/share/applications ~/.config/systemd/user
ln -sfn "$here/zorro-devs" ~/.local/bin/zorro-devs
ln -sfn "$here/zorro-devs.desktop" ~/.local/share/applications/zorro-devs.desktop
ln -sfn "$here/zorro-devs.service" ~/.config/systemd/user/zorro-devs.service
"$here/zorro-devs" fill
systemctl --user daemon-reload
systemctl --user enable zorro-devs.service >/dev/null 2>&1
systemctl --user restart zorro-devs.service
echo "DEVS runs: http://127.0.0.1:8098 (also from the home network and NetBird)"
