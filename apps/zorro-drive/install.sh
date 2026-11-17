#!/usr/bin/env bash
# Install the Drive app for the current user (no sudo). Safe to rerun.
# Needs: rclone (update-extras.sh), python3-gi + gir1.2-gtk-3.0, inotify-tools, fuse3.
set -euo pipefail
here=$(dirname "$(realpath "$0")")

mkdir -p ~/.local/bin ~/.local/share/applications ~/.config/systemd/user
ln -sfn "$here/zorro-drive" ~/.local/bin/zorro-drive
ln -sfn "$here/zorro-drive.desktop" ~/.local/share/applications/zorro-drive.desktop
for unit in "$here"/systemd/*; do
  ln -sfn "$unit" ~/.config/systemd/user/"$(basename "$unit")"
done

if systemctl --user daemon-reload 2>/dev/null; then
  # the old single-account setup this app replaces
  systemctl --user disable --now rclone-gdrive.service gdrive-sync.timer 2>/dev/null || true
  # watcher: uploads saved files; timer: Drive -> laptop every 30 min, only on the charger
  systemctl --user enable zorro-drive-watch.service zorro-drive-sync.timer
  systemctl --user start zorro-drive-watch.service zorro-drive-sync.timer
  echo "Drive app installed (rofi: Drive)"
else
  echo "Drive app linked; no user session bus, so after login run:"
  echo "  systemctl --user enable --now zorro-drive-watch.service zorro-drive-sync.timer"
fi
