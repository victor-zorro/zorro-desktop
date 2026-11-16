#!/usr/bin/env bash
# Install the 'zorro' nody-greeter theme. Run as root (sudo -A).
#   install-theme.sh           copy theme + select it in web-greeter.yml
#   install-theme.sh --enable  also make nody-greeter the LightDM greeter
set -euo pipefail
cd "$(dirname "$0")"

[[ -x /opt/nody-greeter/nody-greeter ]] || { echo "nody-greeter not installed (run update-extras.sh)"; exit 1; }

T=/usr/share/web-greeter/themes/zorro
rm -rf "$T"
cp -r themes/zorro "$T"
rm -rf "$T/dev"                       # browser-preview mock, not needed in the greeter
sed -i -E 's/^(\s*theme:).*/\1 zorro/' /etc/lightdm/web-greeter.yml
echo "theme installed: $T"

if [[ ${1:-} == --enable ]]; then
  install -Dm644 ../lightdm/60-nody-greeter.conf /etc/lightdm/lightdm.conf.d/60-nody-greeter.conf
  echo "nody-greeter enabled (LightDM reads config only at start: reboot or restart lightdm)"
fi
