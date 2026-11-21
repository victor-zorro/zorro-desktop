# Put in /etc/profile.d by the Zorro installer ISO. The first time you log in at the
# screen of the new system, finish the desktop setup from ~/zorro-desktop (asks your
# password). When it has finished once, this does nothing; delete the file whenever you like.
zorro_first_login() {
  state=$HOME/.local/state
  repo=$HOME/zorro-desktop
  [ -f "$state/zorro-first-login.done" ] && return 0
  if [ -x "$repo/install.sh" ]; then
    echo
    echo "Zorro desktop: finishing the setup. Press Ctrl+C within 10 seconds to skip;"
    echo "it is offered again at the next login."
    sleep 10 || return 0
    mkdir -p "$state"
    if flock -n "$state/zorro-first-login.lock" "$repo/install.sh"; then
      touch "$state/zorro-first-login.done" "$state/zorro-open-connect"
      echo "Zorro desktop: set up. Log out and in again, or run startx, for the desktop."
    else
      echo "Not finished: log in again to retry, or run ~/zorro-desktop/install.sh"
    fi
  elif [ ! -e "$repo" ] && command -v curl >/dev/null; then
    echo
    echo "Zorro desktop: this system is new. Installing the desktop now (needs the internet)."
    echo "Press Ctrl+C within 10 seconds to skip; it is offered again at the next login."
    sleep 10 || return 0
    curl -fsSL https://raw.githubusercontent.com/victor-zorro/zorro-desktop/main/bootstrap.sh | bash \
      || echo "Not finished: log in again to retry, or run ~/zorro-desktop/install.sh"
  fi
}

if [ "$(id -u)" -ge 1000 ] && [ -z "${SSH_CONNECTION:-}" ] && [ -t 0 ] \
   && [ -z "${ZORRO_FIRST_LOGIN:-}" ]; then
  export ZORRO_FIRST_LOGIN=1
  zorro_first_login
fi
unset -f zorro_first_login
