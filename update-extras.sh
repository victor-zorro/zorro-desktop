#!/usr/bin/env bash
# Install or update apps shipped as .deb on GitHub releases.
set -euo pipefail

ARCH=$(dpkg --print-architecture)
if [[ $ARCH == amd64 ]]; then
  MQTTX_PAT='amd64\.deb$'; LS_PAT='linux-x86-64\.deb$'
else
  MQTTX_PAT='arm64\.deb$'; LS_PAT='linux-arm-64\.deb$'
fi

gh_deb() {
  local repo=$1 pattern=$2 url
  url=$(curl -fsSL "https://api.github.com/repos/$repo/releases/latest" \
    | grep -o '"browser_download_url": *"[^"]*"' | cut -d'"' -f4 \
    | grep -E "$pattern" | head -n1)
  if [[ -z $url ]]; then echo "!! No .deb found for $repo ($ARCH)"; return 1; fi
  echo "==> $repo: $(basename "$url")"
  curl -fL "$url" -o "/tmp/${repo##*/}.deb"
  sudo apt install -y "/tmp/${repo##*/}.deb"
}

gh_deb emqx/MQTTX "$MQTTX_PAT"
gh_deb localsend/localsend "$LS_PAT"

# --- rclone (Google Drive mount/sync) ------------------------------------
# Official build: Debian's package is too old for reliable bisync.
echo "==> rclone"
sudo apt install -y --no-install-recommends fuse3 unzip
curl -fsSL https://rclone.org/install.sh | sudo bash || true   # exits 3 when already current

# --- Blender (latest official build in /opt/blender) ----------------------
if [[ $ARCH == amd64 ]]; then
  series=$(curl -fsSL https://download.blender.org/release/ \
    | grep -oE 'Blender[0-9]+\.[0-9]+/' | sort -uV | tail -n1)
  file=$(curl -fsSL "https://download.blender.org/release/$series" \
    | grep -oE 'blender-[0-9.]+-linux-x64\.tar\.xz' | sort -uV | tail -n1)
  if [[ -z $file ]]; then
    echo "!! Could not find a Blender build"
  elif [[ -f /opt/blender/.version && $(cat /opt/blender/.version) == "$file" ]]; then
    echo "==> Blender: ${file%.tar.xz} already installed"
  else
    echo "==> Blender: $file"
    # runtime libraries the official build expects on a minimal system
    sudo apt install -y --no-install-recommends xz-utils libxi6 libxxf86vm1 \
      libxfixes3 libxrender1 libxkbcommon0 libsm6 libgl1 libegl1
    curl -fL "https://download.blender.org/release/$series$file" -o /tmp/blender.tar.xz
    sudo rm -rf /opt/blender && sudo mkdir -p /opt/blender
    sudo tar -xJf /tmp/blender.tar.xz -C /opt/blender --strip-components=1
    echo "$file" | sudo tee /opt/blender/.version >/dev/null
    sudo ln -sf /opt/blender/blender /usr/local/bin/blender
    sed 's|^Exec=.*|Exec=/opt/blender/blender %f|; s|^Icon=.*|Icon=/opt/blender/blender.svg|' \
      /opt/blender/blender.desktop | sudo tee /usr/share/applications/blender.desktop >/dev/null
    rm -f /tmp/blender.tar.xz
  fi
fi
