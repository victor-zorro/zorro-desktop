#!/usr/bin/env bash
# Install zorro-dm (display manager + greeter + lock screen). Run as root.
#   install.sh           install/update files (safe to rerun)
#   install.sh --enable  also make zorro-dm the display manager (instead of LightDM)
set -euo pipefail
cd "$(dirname "$0")"

id _zorro-dm >/dev/null 2>&1 || useradd --system --home-dir /var/lib/zorro-dm \
  --create-home --shell /usr/sbin/nologin --comment "zorro-dm greeter" _zorro-dm
usermod -aG video,render _zorro-dm          # GPU for the WebGL animation

install -Dm755 zorro-dm /usr/local/sbin/zorro-dm
install -Dm755 zorro-greeter /usr/local/bin/zorro-greeter
install -Dm755 zorro-lock /usr/local/bin/zorro-lock
for f in pam/*; do install -Dm644 "$f" "/etc/pam.d/$(basename "$f")"; done
install -Dm644 zorro-dm.service /etc/systemd/system/zorro-dm.service
# hibernate: the password once again before face unlock
install -Dm755 zorro-dm.sleep /usr/lib/systemd/system-sleep/zorro-dm
rm -rf /usr/share/zorro-dm/theme
mkdir -p /usr/share/zorro-dm
cp -r theme /usr/share/zorro-dm/theme
rm -rf /usr/share/zorro-dm/theme/dev
systemctl daemon-reload
echo "zorro-dm installed"

if [[ ${1:-} == --enable ]]; then
  systemctl disable lightdm.service 2>/dev/null || true
  systemctl enable --force zorro-dm.service
  echo /usr/local/sbin/zorro-dm > /etc/X11/default-display-manager
  echo "zorro-dm enabled (reboot, or: systemctl stop lightdm; systemctl start zorro-dm)"
fi
