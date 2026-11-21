#!/usr/bin/env bash
# ThinkPad app: system part (run with sudo). Safe to rerun.
#   udev rule : brightness + ThinkPad LEDs writable for group video,
#               ThinkPad Extra Buttons readable for the logged-in user
#   modules   : LED blink patterns (heartbeat, timer) for the red dot
#   helper    : root-owned copy + polkit rule, for power mode / charge limits (pkexec)
#   zorro-lte : root-owned copy + polkit rule, for the Mobile tab (modem, SIM PIN, data)
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
install -Dm755 -o root -g root "$here/zorro-thinkpad-helper" \
    /usr/local/libexec/zorro-lang-helper           # same code, only spell-check dictionaries
install -Dm755 -o root -g root "$here/zorro-thinkpad-helper" \
    /usr/local/libexec/zorro-net-helper            # same code, only: the cable to NetworkManager
install -Dm755 -o root -g root "$here/zorro-usb-helper" \
    /usr/local/libexec/zorro-usb-helper            # Connect: write the installer to a USB stick
# LTE modem tool for the Zorro app's Mobile tab: root-owned copy, run through polkit
install -d -m755 -o root -g root /usr/local/lib/zorro-lte /usr/local/lib/zorro-lte/xmm7360
install -m755 -o root -g root "$here/zorro-lte" /usr/local/lib/zorro-lte/zorro-lte
install -m644 -o root -g root "$here"/xmm7360/*.py "$here/xmm7360/NOTICE" \
    /usr/local/lib/zorro-lte/xmm7360/
install -Dm644 "$here/org.zorro.thinkpad.policy" \
    /usr/share/polkit-1/actions/org.zorro.thinkpad.policy

udevadm control --reload
udevadm trigger --action=add --subsystem-match=backlight --subsystem-match=leds
udevadm trigger --action=change --subsystem-match=input
echo "zorro-thinkpad: udev rule, LED modules and power helper installed"
