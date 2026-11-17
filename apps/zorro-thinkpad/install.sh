#!/usr/bin/env bash
# ThinkPad app: system part (run with sudo). Safe to rerun.
#   udev rule : brightness + ThinkPad LEDs writable for group video,
#               ThinkPad Extra Buttons readable for the logged-in user
#   modules   : LED blink patterns (heartbeat, timer) for the red dot
#   helper    : root-owned copy + polkit rule, for power mode / charge limits (pkexec)
# The user part (links, autostart) is install-user.sh, run by the main install.sh.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
here=$(dirname "$(realpath "$0")")

rm -f /etc/udev/rules.d/90-zorro-thinkpad.rules            # old name, ran too late
install -Dm644 "$here/70-zorro-thinkpad.rules" /etc/udev/rules.d/70-zorro-thinkpad.rules

printf 'ledtrig-heartbeat\nledtrig-timer\n' > /etc/modules-load.d/zorro-thinkpad.conf
modprobe -a ledtrig-heartbeat ledtrig-timer || true

# a copy, not a link: polkit runs it as root, so the user must not be able to change it
install -Dm755 -o root -g root "$here/zorro-thinkpad-helper" \
    /usr/local/libexec/zorro-thinkpad-helper
install -Dm755 -o root -g root "$here/zorro-thinkpad-helper" \
    /usr/local/libexec/zorro-look-helper           # same code, only the login look
install -Dm644 "$here/org.zorro.thinkpad.policy" \
    /usr/share/polkit-1/actions/org.zorro.thinkpad.policy

udevadm control --reload
udevadm trigger --action=add --subsystem-match=backlight --subsystem-match=leds
udevadm trigger --action=change --subsystem-match=input
echo "zorro-thinkpad: udev rule, LED modules and power helper installed"
