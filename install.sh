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
  pkg=$(basename "$pkg")
  # systemd: link the unit files, not the folder, so 'systemctl --user enable'
  # writes its *.wants links in ~ instead of inside the repo
  if [[ $pkg == systemd && -L $HOME/.config/systemd ]]; then
    stow -d config -t "$HOME" -D systemd
  fi
  opts=(); [[ $pkg == systemd ]] && opts=(--no-folding)
  stow -d config -t "$HOME" "${opts[@]}" --restow "$pkg"
done

log "Default apps: Thunar (folders), Ristretto (images), VLC (video, audio)"
# xdg-mime only changes these types in ~/.config/mimeapps.list; PDF/web stay with Firefox
declare -A DEFAULT_APPS=(
  [thunar.desktop]="inode/directory"
  [org.xfce.ristretto.desktop]="image/jpeg image/png image/gif image/webp image/bmp image/tiff image/svg+xml image/heic"
  [vlc.desktop]="video/mp4 video/x-matroska video/webm video/quicktime video/x-msvideo video/mpeg video/ogg audio/mpeg audio/flac audio/ogg audio/x-wav audio/mp4 audio/aac"
)
for app in "${!DEFAULT_APPS[@]}"; do
  [[ -f /usr/share/applications/$app ]] && xdg-mime default "$app" ${DEFAULT_APPS[$app]}
done

log "Drive app (apps/zorro-drive)"
apps/zorro-drive/install.sh

log "Screenshot overlay (apps/zorro-shot)"
apps/zorro-shot/install.sh
log "User folders (Downloads, Pictures, Documents) for browsers and file dialogs"
for kv in DOWNLOAD:Downloads PICTURES:Pictures DOCUMENTS:Documents; do
  mkdir -p "$HOME/${kv#*:}"
  xdg-user-dirs-update --set "${kv%%:*}" "$HOME/${kv#*:}"
done
log "Info circle on the desktop (apps/zorro-orb)"
apps/zorro-orb/install.sh

# Scripts in ~/.local/bin on PATH for every shell
grep -qF 'PATH="$HOME/.local/bin:$PATH"' "$HOME/.bashrc" \
  || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"

log "sudo -A: graphical password dialog"
ASKPASS=/usr/lib/openssh/gnome-ssh-askpass
if [[ -x $ASKPASS ]] && ! grep -q '^Path askpass' /etc/sudo.conf 2>/dev/null; then
  echo "Path askpass $ASKPASS" | sudo tee -a /etc/sudo.conf >/dev/null
fi

log "Dark mode preference"
dbus-run-session -- gsettings set org.gnome.desktop.interface color-scheme prefer-dark || true
dbus-run-session -- gsettings set org.gnome.desktop.interface gtk-theme Adwaita-dark || true

if has laptop; then
  sudo install -Dm644 system/tlp/10-battery.conf /etc/tlp.d/10-battery.conf
  # Lid: suspend, hibernate after 10 min (swap must be >= RAM, resume= in initramfs)
  sudo install -Dm644 system/systemd/logind-lid.conf /etc/systemd/logind.conf.d/zorro-lid.conf
  sudo install -Dm644 system/systemd/sleep-zorro.conf /etc/systemd/sleep.conf.d/zorro.conf
  # ThinkPad app (apps/zorro-thinkpad): Fn keys, indicator, LEDs
  if [[ -d /sys/devices/platform/thinkpad_acpi ]]; then
    sudo apps/zorro-thinkpad/install.sh
    apps/zorro-thinkpad/install-user.sh
  fi
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
# zorro-dm: our own display manager, animated greeter and lock screen (apps/zorro-dm).
# LightDM + GTK greeter stay installed as fallback:
#   sudo systemctl disable zorro-dm && sudo systemctl enable --force lightdm
sudo install -Dm644 system/lightdm/50-zorro.conf /etc/xdg/lightdm/lightdm-gtk-greeter.conf.d/50-zorro.conf
sudo rm -f /etc/lightdm/lightdm.conf.d/60-nody-greeter.conf   # old nody web greeter
sudo apps/zorro-dm/install.sh --enable
sudo systemctl set-default graphical.target

# --- Done ---------------------------------------------------------------
log "Done. Manual follow-ups:"
echo " - Reboot, then log in to the Openbox session"
echo " - netbird up --management-url https://<your-server> --setup-key <key>"
echo " - Google Drive: open the Drive app (rofi: Drive), add an account, pick folders"
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
