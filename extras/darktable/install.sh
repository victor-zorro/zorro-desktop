#!/usr/bin/env bash
# darktable from the Debian/Ubuntu package list (darktable). Asks for your password. Safe to rerun.
set -euo pipefail
. "$(dirname "$(realpath "$0")")/../common.sh"
apt_app "darktable" darktable
