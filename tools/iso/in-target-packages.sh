#!/bin/sh
# Runs in the new system (in-target): installs the desktop's apt lists the way
# install.sh picks them. Argument: the packages folder of the repo snapshot.
dir=$1
export DEBIAN_FRONTEND=noninteractive
say() { echo "$(date '+%F %T') $*"; }
apt_install() { apt-get install -y --no-install-recommends "$@"; }

lists=common
if systemd-detect-virt -q 2>/dev/null || grep -q '^flags.* hypervisor' /proc/cpuinfo; then
  lists="$lists vm"
fi
if ls /sys/class/power_supply/BAT* >/dev/null 2>&1; then
  lists="$lists laptop"
  [ -f "$dir/laptop-debian.txt" ] && lists="$lists laptop-debian"
fi
say "lists: $lists"

wanted=
for list in $lists; do
  [ -f "$dir/$list.txt" ] || { say "missing list $list.txt"; continue; }
  wanted="$wanted $(grep -vE '^[[:space:]]*(#|$)' "$dir/$list.txt")"
done
count=$(echo $wanted | wc -w)
say "packages asked for: $count"

apt-get update || say "apt update failed"
if apt_install $wanted; then
  say "all $count packages installed"
  exit 0
fi

say "one call failed: trying the packages one by one"
failed=
for pkg in $wanted; do
  apt_install "$pkg" || { say "FAILED: $pkg"; failed="$failed $pkg"; }
done
say "packages failed:${failed:- none}"
exit 0
