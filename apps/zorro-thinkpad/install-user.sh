#!/usr/bin/env bash
# Zorro app + ThinkPad keys: user part (no sudo). Safe to rerun. keyd starts from Openbox autostart.
set -euo pipefail
here=$(dirname "$(realpath "$0")")
mkdir -p ~/.local/bin ~/.local/share/applications
ln -sfn "$here/zorro-thinkpad" ~/.local/bin/zorro-thinkpad
ln -sfn "$here/zorro-thinkpad" ~/.local/bin/zorro-settings      # the app: no arguments
rm -f ~/.local/share/applications/zorro-thinkpad.desktop         # old name
for app in settings system connect; do      # Desktop, System, Connect: one program, three entries
  ln -sfn "$here/zorro-$app.desktop" ~/.local/share/applications/zorro-$app.desktop
done
echo "zorro-thinkpad linked (rofi: Zorro)"
