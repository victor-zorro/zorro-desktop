# Put in /etc/profile.d by the Zorro installer ISO: the first time you log in at the
# screen of a fresh system, fetch the Zorro desktop and install it (asks your password).
# Once ~/zorro-desktop is there this does nothing; delete this file whenever you like.
if [ "$(id -u)" -ge 1000 ] && [ ! -e "$HOME/zorro-desktop" ] && [ -z "${SSH_CONNECTION:-}" ] \
   && [ -t 0 ] && [ -z "${ZORRO_FIRST_LOGIN:-}" ] && command -v curl >/dev/null; then
  export ZORRO_FIRST_LOGIN=1
  echo
  echo "Zorro desktop: this system is new. Installing the desktop now (needs the internet)."
  echo "Press Ctrl+C within 10 seconds to skip; it is offered again at the next login."
  if sleep 10; then
    curl -fsSL https://raw.githubusercontent.com/victor-zorro/zorro-desktop/main/bootstrap.sh | bash \
      || echo "Not finished: log in again to retry, or run ~/zorro-desktop/install.sh"
  fi
fi
