#!/usr/bin/env bash
# Transfer's root part (sudo): the accounts helper + its polkit rule. Safe to rerun.
set -euo pipefail
here=$(dirname "$(realpath "$0")")
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
# a copy, not a link: polkit runs it as root, so the user must not be able to change it
install -Dm755 -o root -g root "$here/zorro-accounts-helper" \
    /usr/local/libexec/zorro-accounts-helper
install -Dm644 -o root -g root "$here/org.zorro.transfer.policy" \
    /usr/share/polkit-1/actions/org.zorro.transfer.policy
echo "Transfer: accounts helper installed"
