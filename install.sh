#!/usr/bin/env bash
# Desktop bootstrap: Debian 13 or Ubuntu 24.04 (minimal) + Openbox
#   ./install.sh           auto-detect profiles (vm / nvidia / laptop)
#   ./install.sh laptop    force extra profiles instead of detecting
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
has() { [[ " ${PROFILES[*]} " == *" $1 "* ]]; }
install_list() {
  grep -vE '^\s*(#|$)' "packages/$1.txt" | xargs sudo apt install -y --no-install-recommends
}

# --- Architecture + distro guard ----------------------------------------
ARCH=$(dpkg --print-architecture)
case "$ARCH" in
  amd64|arm64) ;;
  *) echo "Unsupported arch: $ARCH (need amd64 or arm64)"; exit 1 ;;
esac

. /etc/os-release
DISTRO=$ID
case "$DISTRO" in
  debian|ubuntu) ;;
  *) echo "Unsupported distro: $DISTRO (need debian or ubuntu)"; exit 1 ;;
esac

# --- Profiles -----------------------------------------------------------
sudo apt update
sudo apt install -y --no-install-recommends pciutils curl gnupg nano ca-certificates
PROFILES=(common)
if [[ $# -gt 0 ]]; then
  PROFILES+=("$@")
else
  if [[ "$(systemd-detect-virt || true)" != "none" ]]; then PROFILES+=(vm); fi
  if lspci | grep -qi nvidia; then PROFILES+=(nvidia); fi
  if compgen -G "/sys/class/power_supply/BAT*" >/dev/null; then PROFILES+=(laptop); fi
fi
log "Distro: $DISTRO $VERSION_ID | Arch: $ARCH | Profiles: ${PROFILES[*]}"

# --- Base packages ------------------------------------------------------
log "Base desktop packages"
install_list common
has vm     && install_list vm
has laptop && install_list laptop
if has laptop && [[ -f packages/laptop-$DISTRO.txt ]]; then install_list "laptop-$DISTRO"; fi
has laptop && sudo usermod -aG video "$USER"   # brightnessctl without sudo

# --- Apt repositories ---------------------------------------------------
log "Adding apt repositories"
sudo install -d -m 0755 /etc/apt/keyrings

# Mozilla (Firefox .deb; pin also beats Ubuntu's snap transitional package)
curl -fsSL https://packages.mozilla.org/apt/repo-signing-key.gpg \
  | sudo tee /etc/apt/keyrings/packages.mozilla.org.asc >/dev/null
echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" \
  | sudo tee /etc/apt/sources.list.d/mozilla.list >/dev/null
printf 'Package: *\nPin: origin packages.mozilla.org\nPin-Priority: 1000\n' \
  | sudo tee /etc/apt/preferences.d/mozilla >/dev/null

# Anthropic (Claude desktop)
sudo curl -fsSLo /usr/share/keyrings/claude-desktop-archive-keyring.asc \
  https://downloads.claude.ai/claude-desktop/key.asc
echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/claude-desktop-archive-keyring.asc] https://downloads.claude.ai/claude-desktop/apt/stable stable main" \
  | sudo tee /etc/apt/sources.list.d/claude-desktop.list >/dev/null

# NetBird
curl -fsSL https://pkgs.netbird.io/debian/public.key \
  | sudo gpg --dearmor --yes -o /usr/share/keyrings/netbird-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/netbird-archive-keyring.gpg] https://pkgs.netbird.io/debian stable main" \
  | sudo tee /etc/apt/sources.list.d/netbird.list >/dev/null

# Signal (amd64 only)
if [[ $ARCH == amd64 ]]; then
  curl -fsSL https://updates.signal.org/desktop/apt/keys.asc \
    | sudo gpg --dearmor --yes -o /usr/share/keyrings/signal-desktop-keyring.gpg
  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/signal-desktop-keyring.gpg] https://updates.signal.org/desktop/apt xenial main" \
    | sudo tee /etc/apt/sources.list.d/signal-xenial.list >/dev/null
fi

sudo apt update

# --- Apps ---------------------------------------------------------------
log "Apps from apt repositories"
sudo apt install -y --no-install-recommends firefox netbird
if [[ $ARCH == amd64 ]]; then sudo apt install -y --no-install-recommends signal-desktop; fi
# Claude desktop WITH recommends: pulls in QEMU/OVMF/virtiofsd for Cowork
sudo apt install -y claude-desktop
sudo usermod -aG kvm "$USER"

log "Claude Code CLI"
command -v claude >/dev/null || [[ -x "$HOME/.local/bin/claude" ]] \
  || curl -fsSL https://claude.ai/install.sh | bash

log "Apps from GitHub releases, rclone, Blender"
./update-extras.sh

# --- Hardware profiles --------------------------------------------------
if has nvidia; then
  log "NVIDIA driver"
  if [[ $DISTRO == ubuntu ]]; then
    sudo apt install -y ubuntu-drivers-common
    sudo ubuntu-drivers install
  else
    # Debian: the driver lives in contrib/non-free
    [[ -f /etc/apt/sources.list ]] && sudo sed -i -E \
      's/^(deb(-src)? .*) main non-free-firmware$/\1 main contrib non-free non-free-firmware/' \
      /etc/apt/sources.list
    [[ -f /etc/apt/sources.list.d/debian.sources ]] && sudo sed -i -E \
      's/^Components: main non-free-firmware$/Components: main contrib non-free non-free-firmware/' \
      /etc/apt/sources.list.d/debian.sources
    sudo apt update
    sudo apt install -y linux-headers-"$ARCH" nvidia-driver firmware-misc-nonfree
  fi
fi

# --- Configs ------------------------------------------------------------
# rc.xml = the system default (Alt+Tab etc.) plus our keybinds, built once.
# After that the repo copy is the one to edit.
RCXML=config/openbox/.config/openbox/rc.xml
if [[ ! -f $RCXML ]]; then
  log "Building Openbox rc.xml from system default + keybinds"
  sed '/<keyboard>/r templates/openbox-keybinds.xml' /etc/xdg/openbox/rc.xml > "$RCXML"
fi

log "Linking configs with stow"
mkdir -p "$HOME/.config" "$HOME/.local/bin"
for pkg in config/*/; do
  stow -d config -t "$HOME" --restow "$(basename "$pkg")"
done

log "Dark mode preference"
dbus-run-session -- gsettings set org.gnome.desktop.interface color-scheme prefer-dark || true
dbus-run-session -- gsettings set org.gnome.desktop.interface gtk-theme Adwaita-dark || true

if has laptop; then
  sudo install -Dm644 system/tlp/10-battery.conf /etc/tlp.d/10-battery.conf
fi

log "Time zone: Europe/Berlin"
sudo timedatectl set-timezone Europe/Berlin
sudo timedatectl set-ntp true || true

# --- Locale: UTF-8, English language, European formats -------------------
log "Locale: en_US.UTF-8 with en_IE formats (24h, A4, metric, €)"
sudo apt install -y --no-install-recommends locales
if [[ $DISTRO == debian ]]; then
  # Debian's locale-gen ignores arguments; it builds what /etc/locale.gen lists
  sudo sed -i -E 's/^# *(en_US\.UTF-8 UTF-8)/\1/; s/^# *(en_IE\.UTF-8 UTF-8)/\1/' /etc/locale.gen
  sudo locale-gen
else
  sudo locale-gen en_US.UTF-8 en_IE.UTF-8
fi
sudo update-locale LANG=en_US.UTF-8 \
  LC_TIME=en_IE.UTF-8 LC_PAPER=en_IE.UTF-8 \
  LC_MEASUREMENT=en_IE.UTF-8 LC_MONETARY=en_IE.UTF-8

# --- Keyboard: US layout, € on AltGr+5 (system-wide, incl. login screen) --
log "Keyboard: US, euro on AltGr+5"
sudo tee /etc/default/keyboard >/dev/null <<'KBD'
XKBMODEL="pc105"
XKBLAYOUT="us"
XKBVARIANT=""
XKBOPTIONS="lv3:ralt_switch,eurosign:5"
BACKSPACE="guess"
KBD
sudo udevadm trigger --subsystem-match=input --action=change || true

# --- Login screen -------------------------------------------------------
# LightDM has no [Install] section; it runs via display-manager.service
echo /usr/sbin/lightdm | sudo tee /etc/X11/default-display-manager >/dev/null
sudo DEBIAN_FRONTEND=noninteractive dpkg-reconfigure lightdm
sudo systemctl set-default graphical.target

# --- Done ---------------------------------------------------------------
log "Done. Manual follow-ups:"
echo " - Reboot, then log in to the Openbox session"
echo " - netbird up --management-url https://<your-server> --setup-key <key>"
echo " - Google Drive: rclone config  (new remote named 'gdrive', type 'drive'), then:"
echo "   systemctl --user enable --now rclone-gdrive   -> whole Drive online in ~/GoogleDrive"
echo " - Offline folders: list them in ~/.config/gdrive-sync/folders.list, run gdrive-sync once,"
echo "   then: systemctl --user enable --now gdrive-sync.timer  -> ~/DriveOffline, every 10 min"
has nvidia && echo " - Install DaVinci Resolve manually (Blackmagic download), then reboot for the driver"
if has laptop; then
  if [[ $DISTRO == debian ]]; then
    echo " - Wi-Fi (at the laptop, not over SSH): in /etc/network/interfaces keep only the"
    echo "   'lo' lines, then: sudo systemctl restart NetworkManager && nmtui"
  else
    echo " - Wi-Fi (at the laptop, not over SSH): switch netplan renderer to NetworkManager, then nmtui"
  fi
fi
has vm && echo " - Cowork in a VM needs nested virtualization: set Proxmox CPU type to 'host'"
exit 0
