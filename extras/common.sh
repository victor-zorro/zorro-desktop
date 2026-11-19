# shared by extras/<id>/install.sh (sourced)
as_root() {               # a password prompt in the desktop (pkexec), sudo in a terminal
  if [[ -n ${DISPLAY:-} ]] && command -v pkexec >/dev/null && [[ ! -t 0 ]]; then pkexec "$@"; else sudo "$@"; fi
}
gh_asset() {              # gh_asset owner/repo regex: URL of the newest release's matching file
  curl -fsSL "https://api.github.com/repos/$1/releases/latest" | grep -o '"browser_download_url": *"[^"]*"' \
    | cut -d'"' -f4 | grep -E "$2" | head -n1
}
desktop_entry() {         # desktop_entry id "Name" exec icon "Comment"
  mkdir -p ~/.local/share/applications
  cat > ~/.local/share/applications/"$1".desktop <<DESK
[Desktop Entry]
Type=Application
Name=$2
Comment=$5
Exec=$3
Icon=$4
Categories=Development;Game;
DESK
}
