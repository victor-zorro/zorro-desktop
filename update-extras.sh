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
  local repo=$1 pattern=$2 pkg=$3 json url tag have
  # a failed download (e.g. GitHub's limit for anonymous calls) skips this app, not the rest
  json=$(curl -fsSL "https://api.github.com/repos/$repo/releases/latest") || json=''
  tag=$(grep -m1 -o '"tag_name": *"[^"]*"' <<<"$json" | cut -d'"' -f4) || true
  have=$(dpkg-query -W -f='${Version}' "$pkg" 2>/dev/null) || have=''
  # installed already at this release? (versions like 1.18.2+64 start with the tag)
  if [[ -n $tag && -n $have && ( $have == "${tag#v}" || $have == "${tag#v}"[+~-]* ) ]]; then
    echo "==> $repo: $pkg $have is current"
    return 0
  fi
  url=$(grep -o '"browser_download_url": *"[^"]*"' <<<"$json" | cut -d'"' -f4 \
    | grep -E "$pattern" | head -n1) || true
  if [[ -z $url ]]; then echo "!! No .deb found for $repo ($ARCH), skipped"; return 0; fi
  echo "==> $repo: $(basename "$url")"
  curl -fL "$url" -o "/tmp/${repo##*/}.deb" || { echo "!! download failed: $repo"; return 0; }
  sudo apt install -y "/tmp/${repo##*/}.deb" || echo "!! install failed: $repo"
}

gh_deb emqx/MQTTX "$MQTTX_PAT" mqttx
gh_deb localsend/localsend "$LS_PAT" localsend
# Obsidian (notes; synced with Obsidian Sync): official .deb, amd64 only
if [[ $ARCH == amd64 ]]; then gh_deb obsidianmd/obsidian-releases 'obsidian_.*_amd64\.deb$' obsidian; fi
# --- rclone (Google Drive mount/sync) ------------------------------------
# Official build: Debian's package is too old for reliable bisync.
echo "==> rclone"
sudo apt install -y --no-install-recommends fuse3 unzip
curl -fsSL https://rclone.org/install.sh | sudo bash || true   # exits 3 when already current

# --- Blender (latest official build in /opt/blender) ----------------------
if [[ $ARCH == amd64 ]]; then
  series=$(curl -fsSL https://download.blender.org/release/ \
    | grep -oE 'Blender[0-9]+\.[0-9]+/' | sort -uV | tail -n1) || true
  file=$(curl -fsSL "https://download.blender.org/release/$series" \
    | grep -oE 'blender-[0-9.]+-linux-x64\.tar\.xz' | sort -uV | tail -n1) || true
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

# --- networkmanager-dmenu (Wi-Fi menu in rofi) ----------------------------
if command -v nmcli >/dev/null; then
  echo "==> networkmanager-dmenu"
  sudo curl -fsSL -o /usr/local/bin/networkmanager_dmenu \
    https://raw.githubusercontent.com/firecat53/networkmanager-dmenu/main/networkmanager_dmenu \
    || echo "!! networkmanager-dmenu download failed"
  sudo chmod +x /usr/local/bin/networkmanager_dmenu
fi
