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
- `apps/<name>/` — our own apps, one folder each with its own install.sh + README (kept separable):
  - `apps/zorro-dm/` — display manager, login + lock screen (zorro-greeter, theme); LightDM stays as fallback
  - `apps/zorro-drive/` — Drive app: Google accounts, synced folders, online mounts (rclone)
  - `apps/zorro-thinkpad/` — the Zorro settings app (zorro-settings, F9) + ThinkPad keys/indicator (keyd), power, LEDs, LTE, hardware
  - `apps/zorro-shot/` — screenshot overlay (PrtSc): region / window / screen to file + clipboard
  - `apps/zorro-dial/` — app launcher: a dial around a clock, 3 rings by usage × 3 category slices (Super tap / Super+Space)
  - `apps/zorro-wall/` — living wallpaper: the login engine (iridescent deep sea + wireframe animal) on the desktop
  - `apps/zorro-orb/` — round info area on the desktop (replaces conky): resting display + 4 hidden hover zones
  - `apps/zorro-fx/` — shared overlay look (particles, lock-screen style) for the indicator and zorro-shot; settings in the ThinkPad app
- Test risky changes in the VM first: `zvm start`, `zvm sync`, `zvm ssh`, `zvm shot`, `zvm reset` (config/bin/.local/bin/zvm)
- `templates/` — snippets used to generate files (Openbox keybinds)
- `extras/` — apps that need a manual download first (e.g. `extras/davinci-resolve/install.sh`)

## Rules
- Every change must also land in the repo so a fresh machine gets it: package → packages/*.txt, config → config/, system file → system/ + an install line in install.sh.
- Keep install.sh safe to rerun: no blind appends; check before adding lines.
- Desktop is windows-only Openbox: no panel, no tray. Launcher = zorro-dial (rofi on Super+Shift+Space), info circle = zorro-orb (conky as fallback), notifications = dunst.
- Keybinds live in config/openbox/.config/openbox/rc.xml (Super = W-). Reload with `openbox --reconfigure`.
- Scripts go in config/bin/.local/bin (on PATH). New apps go in apps/<name>/, not in config/.
- sudo needs a password: put sudo commands in a code block for Vincent to run, don't run them yourself.
- After a working change: git add, commit with a clear message, git push.
