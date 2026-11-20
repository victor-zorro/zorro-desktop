#!/usr/bin/env bash
# Unreal Engine for Linux into ~/UnrealEngine. No root. Epic hands it out only after a login:
#   https://www.unrealengine.com/en-US/linux -> download the Linux zip into ~/Downloads, then
#   extras/unreal-engine/install.sh [path/to/Linux_Unreal_Engine_*.zip]
# The editor writes into its own folder, so it lives in your home folder, not /opt.
set -euo pipefail
. "$(dirname "$(realpath "$0")")/../common.sh"
zip=${1:-$(ls -t ~/Installers/Linux_Unreal_Engine_*.zip ~/Downloads/Linux_Unreal_Engine_*.zip 2>/dev/null | head -n1 || true)}
[[ -f ${zip:-} ]] || { echo "!! no Linux_Unreal_Engine_*.zip in ~/Installers or ~/Downloads (download it from https://www.unrealengine.com/en-US/linux)"; exit 1; }
dest=~/UnrealEngine
need=$(( $(unzip -Zt "$zip" | awk '{print $3}') / 1024 + 1048576 ))      # unpacked size + 1 GB, in kB
free=$(df -Pk "$HOME" | awk 'NR==2{print $4}')
(( free > need )) || { echo "!! not enough room: $(( need / 1048576 )) GB needed, $(( free / 1048576 )) GB free"; exit 1; }
[[ -e $dest ]] && { echo "==> an Unreal Engine is in $dest already: moving it to $dest.old"; rm -rf "$dest.old"; mv "$dest" "$dest.old"; }
echo "==> unpacking $(basename "$zip") into $dest (this takes a while)"
mkdir -p "$dest"
total=$(unzip -Z1 "$zip" | wc -l)
unzip -o "$zip" -d "$dest" | awk -v n="$total" '/inflating:|extracting:|creating:/ { c++; p = int(c * 100 / n); if (p != l) { printf "unpacking %d%%\n", p; l = p; fflush() } }'
# some zips have one folder around everything
if [[ ! -d $dest/Engine ]]; then inner=$(find "$dest" -mindepth 2 -maxdepth 2 -type d -name Engine | head -n1); [[ -n $inner ]] && { top=$(dirname "$inner"); mv "$top"/* "$dest"/; rmdir "$top"; }; fi
ed=$dest/Engine/Binaries/Linux/UnrealEditor
[[ -x $ed ]] || { echo "!! no UnrealEditor in the zip"; exit 1; }
# its logo under a theme name, so the Zorro icon theme makes it black and white like the rest
icon=applications-games
for png in "$dest/Engine/Source/Runtime/Launch/Resources/Linux/UnrealEngine.png" \
           "$dest/Engine/Content/Slate/Starship/Common/UELogo.png"; do
  if [[ -f $png ]]; then
    mkdir -p ~/.local/share/icons/hicolor/256x256/apps
    cp "$png" ~/.local/share/icons/hicolor/256x256/apps/unreal-engine.png
    icon=unreal-engine
    break
  fi
done
desktop_entry unreal-engine "Unreal Engine" "$ed %f" "$icon" "Game engine"
build="$(dirname "$(realpath "$0")")/../../apps/zorro-icons/build-icons"
[[ -x $build ]] && "$build" >/dev/null 2>&1 || true
rm -rf "$dest.old"
keep_installer "$zip"
echo "==> Unreal Engine installed (Dialer: Unreal Engine). The zip is kept in ~/Installers."
