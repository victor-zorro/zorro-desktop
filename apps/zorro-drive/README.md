# Drive (zorro-drive)

Google Drive for the Openbox desktop: several accounts, pick folders to keep on the laptop,
optional online mount per account. rclone does the work underneath.

- **App** (rofi: *Drive*): accounts on the left (+ Account opens Google sign-in), synced folders
  on the right with Sync / Open / Resync / Remove per folder. *Choose folders…* shows the folder
  tree of My Drive and the Shared drives with a checkbox per folder; every ticked folder becomes
  its own entry with its own Sync button (ticking a folder includes its subfolders).
- **Two-way sync** per folder with `rclone bisync`; conflicts keep both versions.
- **One sync at a time** (queue): other folders show "waiting". Each folder shows live
  progress (loading lists → comparing → files x/y, MB, speed, time left, current files);
  the **Activity** list shows every file uploaded ↑, downloaded ↓ or deleted. *Log* shows
  the last rclone run.
- **Google's request limit** ("quota exceeded") pauses a folder and retries after 15 min;
  syncs cut off by a reboot resume by themselves (both done by the watcher).
- **Own Google client ID** per account (*Own Google client ID…*): without it rclone's shared one is
  used, which hits Google's limits and is being retired in 2026. The client ID and tokens live in
  `~/.config/rclone/rclone.conf` only.
- **Battery friendly**: saved files go up ~30 s after the last change (inotify, no polling);
  Drive → laptop runs every 30 min **only on the charger**; on battery press Sync.
- **Online** switch per account: whole Drive at `~/Drive/<account>/Online`, files fetched on open.

| File | What |
|---|---|
| `zorro-drive` | app + CLI: `sync --folder ID [--folder ID…] / --all [--resync]`, `watch`, `status` |
| `systemd/zorro-drive-watch.service` | uploads local saves |
| `systemd/zorro-drive-sync.{service,timer}` | 30-min sync, `ConditionACPower=true` |
| `systemd/zorro-drive-mount@.service` | online mount of one account |

Install (no sudo): `./install.sh`. Needs `rclone` (update-extras.sh), `python3-gi`, `gir1.2-gtk-3.0`,
`inotify-tools`, `fuse3`.
Settings: `~/.config/zorro-drive/config.json`; state + logs: `~/.local/state/zorro-drive/<id>/`;
Google tokens stay in rclone's own `~/.config/rclone/rclone.conf` (never in git).
