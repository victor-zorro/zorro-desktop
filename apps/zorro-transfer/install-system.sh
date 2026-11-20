#!/usr/bin/env bash
# Transfer's root part (sudo): the setup helper + its polkit rule, and the login-look helper
# it uses (also on devices without the ThinkPad app). Safe to rerun.
set -euo pipefail
here=$(dirname "$(realpath "$0")")
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
# copies, not links: polkit runs them as root, so the user must not be able to change them
install -Dm755 -o root -g root "$here/zorro-transfer-helper" \
    /usr/local/libexec/zorro-transfer-helper
install -Dm755 -o root -g root "$here/../zorro-thinkpad/zorro-thinkpad-helper" \
    /usr/local/libexec/zorro-look-helper           # same file the ThinkPad app installs
install -Dm644 -o root -g root "$here/org.zorro.transfer.policy" \
    /usr/share/polkit-1/actions/org.zorro.transfer.policy
rm -f /usr/local/libexec/zorro-accounts-helper     # its old name
echo "Transfer: setup helper installed"
