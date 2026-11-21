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
  - `apps/zorro-thinkpad/` — the Zorro apps in one program (`zorro-settings --app desktop|system|devs|connect`, F9): Desktop (Home, Dialer, wallpaper, windows, look, login, accounts), System (network, audio, power, hardware, screens, ThinkPad), Connect (Transfer, new device: one-liner / ISO / USB, install apps), with DEVS in the same switcher; plus the ThinkPad keys/indicator (keyd), LEDs, LTE. `zsettings/menus.py` says which app holds which menu
  - `apps/zorro-shot/` — screenshot overlay (PrtSc): region / window / screen to file + clipboard
  - `apps/zorro-icons/` — icon theme Zorro-Lucide: official app icons in black and white + white Lucide line icons for symbols (build-icons, mapping.json)
  - `apps/zorro-dial/` — the Dialer: app launcher around the clock; hub in six parts (Apps, Music, Notes, Messages, System, Files) (Super tap / Super+Space)
  - `apps/zorro-wall/` — living wallpaper: the login engine (iridescent deep sea + wireframe animal) on the desktop
  - `apps/zorro-orb/` — round info area on the desktop (replaces conky): resting display + 4 hidden hover zones
  - `apps/zorro-music/` — SoundCloud player (mpv + yt-dlp with your Firefox login); the Dialer's Music part
  - `apps/zorro-winpos/` — windows reopen where you left them (per app place, size, maximized)
  - `apps/zorro-face/` — face unlock with the IR camera (OpenCV YuNet + SFace) for the lock screen / login
  - `apps/zorro-search/` — search notes and documents by meaning (multilingual-e5-small, local service); the Dialer's Notes search
  - `apps/zorro-sweep/` — Sweep notes: rounds of swiping notes left (keep) / right (delete), every 10 kept get dragged into notebooks (best match by meaning); `obsidian-plugin/` = the same game inside Obsidian (laptop + Android, via Sync), published as "Sweep or Keep" (publish-plugin.sh), progress shared in the plugin's data.json
  - `apps/zorro-transfer/` — Transfer: set up another device like this one (Settings, logins, files, `~/Installers`) over the LAN or NetBird; 6-digit code (SPAKE2) → TLS 1.3 PSK, resumable, both sides show progress, runs on in the background; on the new device one password at the start, then unattended (Settings → Desktop → Transfer)
  - `apps/zorro-ai/` — the one AI service all apps ask (socket): Claude (the `claude` CLI), Mistral cloud, local models with llama.cpp; `auto` falls back; `local_only` keeps everything on the laptop
  - `apps/zorro-devs/` — DEVS: catalogue of features, bugs, wishes, backlog and decisions with a test state per device; a web page served from the laptop (port 8098), data in `~/.local/share/zorro-devs` (never in this repo)
  - `apps/zorro-intel/` — Intelligence: search + AI over folders you choose; its own app; the Dialer's AI part is its quick chat
  - `apps/zorro-fx/` — shared overlay look (particles, lock-screen style) for the indicator and zorro-shot; settings in the ThinkPad app; `zorro_style.py` = the one palette + font for all apps
- Test risky changes in the VM first: `zvm start`, `zvm sync`, `zvm ssh`, `zvm shot`, `zvm reset` (config/bin/.local/bin/zvm)
- `tools/` — `check-rules` (file and function size limits of RULES.md), `check-pages` (opens and measures every Settings page in a private test screen), `make-iso` (installer ISO that sets this desktop up)
- `plan/` — the build plan page and `SPEC.md` (decisions and contracts of the last big build)
- `templates/` — snippets used to generate files (Openbox keybinds)
- `extras/` — optional apps, added after the minimal setup: `extras/apps.json` is the list (Godot, Unreal Engine, LocalSend…), each with `extras/<id>/install.sh` (runs as the user, pkexec/sudo for root steps; shared bits in `extras/common.sh`). Installed from Settings → Desktop → Install apps or `zorro-apps install ID`. New optional app = an entry in apps.json + its install.sh. DaVinci Resolve (`extras/davinci-resolve/install.sh`, sudo) is not on the list.

## Rules
- Build and design rules are in `RULES.md` (files ≤ 400 lines, functions ≤ 60, one page = one file, pages fit one screen, menu → submenu → page). Run `tools/check-rules` before every commit.
- Every change must also land in the repo so a fresh machine gets it: package → packages/*.txt, config → config/, system file → system/ + an install line in install.sh.
- Keep install.sh safe to rerun: no blind appends; check before adding lines.
- Desktop is windows-only Openbox: no panel, no tray. Launcher = the Dialer, zorro-dial (rofi on Super+Shift+Space), info circle = zorro-orb (conky as fallback), notifications = dunst.
- Keybinds live in config/openbox/.config/openbox/rc.xml (Super = W-). Reload with `openbox --reconfigure`.
- Scripts go in config/bin/.local/bin (on PATH). New apps go in apps/<name>/, not in config/.
- sudo needs a password: put sudo commands in a code block for Vincent to run, don't run them yourself.
- After a working change: git add, commit with a clear message, git push.
