#!/usr/bin/env bash
# DaVinci Resolve or Resolve Studio on Debian 13. Run with sudo from your own account. Safe to rerun.
# Blackmagic hands out the installer only after a form, so download it yourself first:
#   blackmagicdesign.com/support/family/davinci-resolve-and-fusion -> DaVinci Resolve Studio
#   (Linux), or the free DaVinci Resolve. Studio asks for the licence key at its first start.
#   into ~/Downloads, then:  sudo extras/davinci-resolve/install.sh [path/to/zip]
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
user=${SUDO_USER:?run with sudo from your own account, not as root}
home=$(getent passwd "$user" | cut -d: -f6)
# Studio (paid) when its zip is there, else the free version
zip=${1:-$(ls -t "$home"/Downloads/DaVinci_Resolve_Studio_*_Linux.zip 2>/dev/null | head -n1 || true)}
zip=${zip:-$(ls -t "$home"/Downloads/DaVinci_Resolve_*_Linux.zip 2>/dev/null | head -n1 || true)}
[[ -f ${zip:-} ]] || { echo "no DaVinci_Resolve_*_Linux.zip in $home/Downloads"; exit 1; }
echo "==> $zip"

# what Resolve needs from Debian (the .run checks for Rocky/CentOS names, so we skip that check)
apt-get install -y --no-install-recommends unzip libfuse2t64 libapr1t64 libaprutil1t64 \
  libglu1-mesa libxcb-cursor0 libxcb-composite0 libxcb-damage0 libxcb-xinerama0 \
  libxcb-xinput0 ocl-icd-libopencl1 rocm-opencl-icd clinfo ffmpeg

# on disk, not in /tmp: /tmp is in RAM here (tmpfs) and the 4.5 GB installer unpacks twice
work=$(mktemp -d -p /var/tmp resolve.XXXXXX)
trap 'rm -rf "$work"' EXIT
echo "==> unpacking (a few minutes)"
unzip -q -o "$zip" -d "$work"
run=$(ls "$work"/DaVinci_Resolve_*_Linux.run | head -n1)
chmod +x "$run"
echo "==> installing into /opt/resolve"
TMPDIR=$work SKIP_PACKAGE_CHECK=1 "$run" -i -y  # installs into /opt/resolve + menu entry

# Resolve ships old GLib copies that clash with Debian's: let it use the system ones
mkdir -p /opt/resolve/libs/disabled
for lib in libglib-2.0.so* libgio-2.0.so* libgmodule-2.0.so* libgobject-2.0.so*; do
  for f in /opt/resolve/libs/$lib; do [[ -e $f ]] && mv -f "$f" /opt/resolve/libs/disabled/; done
done

# the GPU (OpenCL through ROCm) needs these groups; a new login makes them active
usermod -aG render,video "$user"
echo "DaVinci Resolve installed. Start it from the launcher (log out and in once first)."
case $zip in
  *Studio*) echo "Studio: enter your licence key at the first start (needs internet once)." ;;
  *) echo "Phone / camera video (H.264, H.265): convert first with  zresolve-convert FILE..." ;;
esac
