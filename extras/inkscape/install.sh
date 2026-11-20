#!/usr/bin/env bash
# Inkscape from the Debian/Ubuntu package list (inkscape). Asks for your password. Safe to rerun.
set -euo pipefail
. "$(dirname "$(realpath "$0")")/../common.sh"
apt_app "Inkscape" inkscape
