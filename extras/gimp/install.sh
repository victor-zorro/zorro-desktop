#!/usr/bin/env bash
# GIMP from the Debian/Ubuntu package list (gimp). Asks for your password. Safe to rerun.
set -euo pipefail
. "$(dirname "$(realpath "$0")")/../common.sh"
apt_app "GIMP" gimp
