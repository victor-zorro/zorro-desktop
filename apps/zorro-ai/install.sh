#!/usr/bin/env bash
# zorro-ai for the current user (no sudo). Safe to rerun.
# Needs only python3. Downloads nothing: the local engine is optional, get it with
#   zorro-ai install-local      llama.cpp's llama-server, ~25 MB
#   zorro-ai pull MODEL_ID      a model from `zorro-ai models`
set -euo pipefail
here=$(dirname "$(realpath "$0")")
config=${XDG_CONFIG_HOME:-$HOME/.config}/zorro-ai
mkdir -p ~/.local/bin ~/.config/systemd/user "$config"
chmod 700 "$config"
ln -sfn "$here/zorro-ai" ~/.local/bin/zorro-ai
ln -sfn "$here/zorro-ai.service" ~/.config/systemd/user/zorro-ai.service
systemctl --user daemon-reload
systemctl --user enable zorro-ai.service >/dev/null 2>&1
systemctl --user restart zorro-ai.service
echo "zorro-ai running (zorro-ai status)"
