# zorro-desktop

Minimal Openbox desktop for Debian 13 / Ubuntu 24.04 (minimal install), the same on every machine.

## New machine

Install Debian 13 netinst (only "SSH server" + "standard system utilities", empty root password), log in as your user, then:

```bash
curl -fsSL https://raw.githubusercontent.com/victor-zorro/zorro-desktop/main/bootstrap.sh | bash
```

Profiles are detected automatically: `vm` (Proxmox guest), `nvidia` (driver), `laptop` (battery present).
Force them with `... | bash -s -- laptop`.

## Keys

| Key | Action |
|---|---|
| Super+Enter | Kitty |
| Super+Space | App launcher (rofi) |
| Super+Tab | Window list |
| Super+Left / Right / Up | Snap half / maximize |
| Super+1..4 | Desktops |
| Super+B | Time, date, battery |
| Right Alt+5 | € |

## Updating

- Config change: edit in `~/zorro-desktop/config/...` (they are symlinked), then `git commit` + `git push`; on other machines `git pull`.
- Apps from apt repos: `sudo apt update && sudo apt upgrade`
- MQTTX, LocalSend, rclone, Blender: `./update-extras.sh`

## Google Drive

- `rclone config` → remote `gdrive`, type `drive` (do this on the machine itself, it opens a browser)
- Whole Drive online: `systemctl --user enable --now rclone-gdrive` → `~/GoogleDrive`
- Offline folders: list them in `~/.config/gdrive-sync/folders.list`, run `gdrive-sync`, then
  `systemctl --user enable --now gdrive-sync.timer` → `~/DriveOffline`, two-way every 10 min
