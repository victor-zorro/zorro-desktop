#!/usr/bin/env bash
# Krita from the Debian/Ubuntu package list (krita). Asks for your password. Safe to rerun.
set -euo pipefail
. "$(dirname "$(realpath "$0")")/../common.sh"
apt_app "Krita" krita
