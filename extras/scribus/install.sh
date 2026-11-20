#!/usr/bin/env bash
# Scribus from the Debian/Ubuntu package list (scribus). Asks for your password. Safe to rerun.
set -euo pipefail
. "$(dirname "$(realpath "$0")")/../common.sh"
apt_app "Scribus" scribus
