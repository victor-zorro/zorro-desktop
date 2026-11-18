#!/usr/bin/env bash
# zorro-music for the current user (no sudo). Safe to rerun. Needs mpv + mpv-mpris
# (packages/laptop.txt); yt-dlp comes fresh from pipx (SoundCloud changes often).
set -euo pipefail
here=$(dirname "$(realpath "$0")")
mkdir -p ~/.local/bin
ln -sfn "$here/zorro-music" ~/.local/bin/zorro-music
if command -v pipx >/dev/null; then
  pipx install yt-dlp >/dev/null 2>&1 || pipx upgrade yt-dlp >/dev/null 2>&1 || true
fi
echo "zorro-music linked (the Dialer's Music part; yt-dlp via pipx)"
