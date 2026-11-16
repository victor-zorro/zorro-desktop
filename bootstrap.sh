#!/usr/bin/env bash
# One-line setup for a fresh Debian 13 / Ubuntu 24.04 minimal machine:
#   curl -fsSL https://raw.githubusercontent.com/victor-zorro/zorro-desktop/main/bootstrap.sh | bash
# Clones (or updates) the repo into ~/zorro-desktop and runs install.sh.
# Extra arguments are passed on:  ... | bash -s -- laptop
set -euo pipefail

main() {
  local repo="https://github.com/victor-zorro/zorro-desktop.git"
  local dir="$HOME/zorro-desktop"

  if [[ $EUID -eq 0 ]]; then
    echo "Run this as your normal user (with sudo rights), not as root."; exit 1
  fi
  command -v sudo >/dev/null || { echo "sudo is missing: install it and add $USER to the sudo group."; exit 1; }

  echo "==> Installing git"
  sudo apt-get update -qq
  sudo apt-get install -y -qq --no-install-recommends git ca-certificates

  if [[ -d $dir/.git ]]; then
    echo "==> Updating $dir"
    git -C "$dir" pull --ff-only
  else
    echo "==> Cloning into $dir"
    git clone "$repo" "$dir"
  fi

  cd "$dir"
  # Give install.sh the real terminal, not the curl pipe
  if [[ -r /dev/tty ]]; then
    ./install.sh "$@" < /dev/tty
  else
    ./install.sh "$@"
  fi
}

# Wrapped in main so nothing runs until the whole script has downloaded
main "$@"
