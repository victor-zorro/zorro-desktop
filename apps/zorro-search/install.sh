#!/usr/bin/env bash
# zorro-search for the current user (no sudo). Safe to rerun.
# Needs python3-onnxruntime python3-sentencepiece python3-numpy (packages/common.txt).
# The model: multilingual-e5-small (MIT), ~120 MB, checked by sha256.
set -euo pipefail
here=$(dirname "$(realpath "$0")")
data=${XDG_DATA_HOME:-$HOME/.local/share}/zorro-search
hf=https://huggingface.co
files=(
  "model_quantized.onnx $hf/Xenova/multilingual-e5-small/resolve/main/onnx/model_quantized.onnx f80102d3f2a1229f387d3c81909990d8945513e347b0eab049f7de3c6f98c193"
  "sentencepiece.bpe.model $hf/intfloat/multilingual-e5-small/resolve/main/sentencepiece.bpe.model cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865"
)
mkdir -p "$data" ~/.local/bin ~/.config/systemd/user
for f in "${files[@]}"; do
    read -r name url sum <<<"$f"
    if ! { [ -f "$data/$name" ] && echo "$sum  $data/$name" | sha256sum -c --quiet >/dev/null 2>&1; }; then
        echo "zorro-search: downloading $name"
        curl -fsSL -o "$data/$name.part" "$url"
        echo "$sum  $data/$name.part" | sha256sum -c --quiet
        mv "$data/$name.part" "$data/$name"
    fi
done
ln -sfn "$here/zorro-search" ~/.local/bin/zorro-search
ln -sfn "$here/zorro-search.service" ~/.config/systemd/user/zorro-search.service
if python3 -c 'import onnxruntime, sentencepiece' 2>/dev/null; then
    systemctl --user daemon-reload
    systemctl --user enable zorro-search.service >/dev/null 2>&1
    systemctl --user restart zorro-search.service
    echo "zorro-search running (the first index takes a few minutes)"
else
    echo "zorro-search linked; needs: sudo apt install python3-onnxruntime python3-sentencepiece"
fi
