# zorro-desktop

Bootstrap + dotfiles for Vincent's minimal Openbox desktop (Debian 13 laptop, Ubuntu 24.04 VMs).
Repo: github.com/victor-zorro/zorro-desktop (public — never commit secrets, tokens or rclone.conf).

## Layout
- `install.sh` — full setup, idempotent, auto-detects profiles (vm / nvidia / laptop) and distro (debian / ubuntu)
- `bootstrap.sh` — curl one-liner for new machines: clones the repo, runs install.sh
- `update-extras.sh` — apps outside apt repos (MQTTX, LocalSend, rclone, Blender, Obsidian, networkmanager-dmenu)
- `packages/*.txt` — apt lists per profile, installed with --no-install-recommends
- `config/<pkg>/` — dotfiles, linked into ~ with GNU Stow (`stow -d config -t ~ --restow <pkg>`)
- `system/` — files for /etc (udev, X11, tlp), copied by install.sh
- `templates/` — snippets used to generate files (Openbox keybinds)

## Rules
- Every change must also land in the repo so a fresh machine gets it: package → packages/*.txt, config → config/, system file → system/ + an install line in install.sh.
- Keep install.sh safe to rerun: no blind appends; check before adding lines.
- Desktop is windows-only Openbox: no panel, no tray. Launcher = rofi, overlay = conky, notifications = dunst.
- Keybinds live in config/openbox/.config/openbox/rc.xml (Super = W-). Reload with `openbox --reconfigure`.
- Scripts go in config/bin/.local/bin (on PATH).
- sudo needs a password: put sudo commands in a code block for Vincent to run, don't run them yourself.
- After a working change: git add, commit with a clear message, git push.
