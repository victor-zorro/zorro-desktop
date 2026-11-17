#!/usr/bin/env bash
# ThinkPad app: system part (run with sudo). Safe to rerun.
#   udev rule: brightness + ThinkPad LEDs writable for group video,
#              ThinkPad Extra Buttons readable for the logged-in user
# The user part (links, autostart) is install-user.sh, run by the main install.sh.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
here=$(dirname "$(realpath "$0")")

rm -f /etc/udev/rules.d/90-zorro-thinkpad.rules            # old name, ran too late
install -Dm644 "$here/70-zorro-thinkpad.rules" /etc/udev/rules.d/70-zorro-thinkpad.rules
udevadm control --reload
udevadm trigger --action=add --subsystem-match=backlight --subsystem-match=leds
udevadm trigger --action=change --subsystem-match=input
echo "zorro-thinkpad: udev rule installed"
