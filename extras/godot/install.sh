#!/usr/bin/env bash
# Godot (standard build) from its official GitHub releases into ~/.local/opt/godot. No root.
# Safe to rerun: installs again only when there is a newer version.
set -euo pipefail
. "$(dirname "$(realpath "$0")")/../common.sh"
case $(uname -m) in x86_64) arch='linux\.x86_64\.zip$' ;; aarch64) arch='linux\.arm64\.zip$' ;; *) echo "!! no Godot build for $(uname -m)"; exit 1 ;; esac
url=$(gh_asset godotengine/godot "^.*/Godot_v[^/]*-stable_$arch") || true
[[ -n ${url:-} ]] || { echo "!! no Godot download found (GitHub limit?), try again later"; exit 1; }
dir=~/.local/opt/godot
if [[ -f $dir/version && $(cat "$dir/version") == "$url" ]]; then echo "==> Godot is current"; exit 0; fi
echo "==> $(basename "$url")"
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
curl -fL --progress-bar "$url" -o "$tmp/godot.zip"
unzip -q "$tmp/godot.zip" -d "$tmp/x"
mkdir -p "$dir" ~/.local/bin
install -m 755 "$tmp"/x/Godot_v* "$dir/godot"
curl -fsSL https://raw.githubusercontent.com/godotengine/godot/master/main/app_icon.png -o "$dir/godot.png" || true
echo "$url" > "$dir/version"
ln -sfn "$dir/godot" ~/.local/bin/godot
desktop_entry godot "Godot" "$dir/godot %f" "$dir/godot.png" "Game engine"
echo "==> Godot installed (Dialer: Godot, or 'godot')"
