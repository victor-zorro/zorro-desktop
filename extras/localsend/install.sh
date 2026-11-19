#!/usr/bin/env bash
# LocalSend (files to phones and computers nearby): the newest .deb from its GitHub releases.
# Asks for your password for the apt step. Safe to rerun.
set -euo pipefail
. "$(dirname "$(realpath "$0")")/../common.sh"
case $(dpkg --print-architecture) in amd64) pat='linux-x86-64\.deb$' ;; arm64) pat='linux-arm-64\.deb$' ;; *) echo "!! no LocalSend for this machine"; exit 1 ;; esac
url=$(gh_asset localsend/localsend "$pat") || true
[[ -n ${url:-} ]] || { echo "!! no LocalSend download found (GitHub limit?), try again later"; exit 1; }
echo "==> $(basename "$url")"
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
curl -fL --progress-bar "$url" -o "$tmp/localsend.deb"
chmod 755 "$tmp"; chmod 644 "$tmp/localsend.deb"       # apt reads it as _apt
as_root apt-get install -y "$tmp/localsend.deb"
echo "==> LocalSend installed"
