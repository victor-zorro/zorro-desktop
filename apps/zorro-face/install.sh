#!/bin/bash
# zorro-face: face unlock with the IR camera. Run as root (sudo); safe to rerun.
#   /usr/local/bin/zorro-face, the two face models (OpenCV zoo, checked by sha256)
#   in /usr/local/share/zorro-face, faces in /var/lib/zorro-face (root only),
#   polkit rule so the Zorro app can enroll your face (asks your password).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }

zoo=https://github.com/opencv/opencv_zoo/raw/main/models
share=/usr/local/share/zorro-face
# finds the face, recognises it, and 68 points for the wireframe in the app's window
models=(
  "$zoo/face_detection_yunet/face_detection_yunet_2023mar.onnx 8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
  "$zoo/face_recognition_sface/face_recognition_sface_2021dec.onnx 0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"
  "https://raw.githubusercontent.com/kurnianggoro/GSOC2017/master/data/lbfmodel.yaml 70dd8b1657c42d1595d6bd13d97d932877b3bed54a95d3c4733a0f740d1fd66b"
)
install -d -m755 "$share"
for m in "${models[@]}"; do
    url=${m% *} sum=${m#* } file="$share/$(basename "${m% *}")"
    if ! echo "$sum  $file" | sha256sum -c --quiet 2>/dev/null; then
        echo "zorro-face: downloading $(basename "$file")"
        curl -fsSL -o "$file.part" "$url"
        echo "$sum  $file.part" | sha256sum -c --quiet
        mv "$file.part" "$file"
        chmod 644 "$file"
    fi
done

install -Dm755 -o root -g root "$here/zorro-face" /usr/local/bin/zorro-face
install -d -m711 /var/lib/zorro-face
install -Dm644 "$here/org.zorro.face.policy" /usr/share/polkit-1/actions/org.zorro.face.policy
echo "zorro-face installed: enroll in the Zorro app (Accounts → Face unlock)"
