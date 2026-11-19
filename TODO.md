# TODO: review of all apps (2026-11-19)

Findings from a full code review: visual arrangement, code, speed. Each item stands on its
own, so it can be picked up one at a time.

## How to work through this list

- Read `CLAUDE.md` first. Its rules apply (no sudo yourself, install.sh stays safe to rerun,
  commit + push after each working change, never commit secrets).
- One item = one commit. Tick the box in this file in the same commit.
- **Line numbers are from 2026-11-19 and will drift.** Find the code by the function or text
  named in the item, and read it before changing it. If the code no longer matches the
  description, skip the item and add a note under it.
- Items marked **(confirm first)** were not proven. Reproduce or measure before changing.
- Test without touching the real desktop: run apps in a user-space Xvfb (display `:77`), on
  copies of notes and config. Never kill processes by name, only by PID you started.
- When an item says "measure", write the before / after number in the commit message.
- Effort: S = under an hour, M = a few hours, L = a day or more.
- Security items for the login / lock screen are in `TODO-private.md` (not in git).

Order: phase 1 first (things that are wrong today), then 2 (quick speed wins), then 3
(shared style and helpers), then 4 (larger jobs). Inside a phase any order works.

---

## Phase 1: wrong today

- [x] **1.1 Drive: a folder that fails its first sync retries forever** (S)
  `apps/zorro-drive/zorro-drive` — `sync_folder`, `cmd_sync` (about lines 199-297).
  A folder with no baseline runs a full `--resync` on every timer run and sends a critical
  notification each time. One folder fails on "can't read dangling shortcut" (about 14
  minutes per run). After `rate_limited` the batch also carries on with the next folders.
  Fix: add `--drive-skip-dangling-shortcuts` to the bisync call; in `--all` runs skip a
  folder whose `last_error` is recent, with a growing back-off (30 min, 1 h, 2 h, max 12 h);
  notify only when the error text changes; break the batch on `rate_limited`.
  Check: `journalctl --user -u zorro-drive-sync` shows the folder synced or skipped.

- [x] **1.2 Drive: timer counts from the start of a run** (S)
  `apps/zorro-drive/systemd/zorro-drive-sync.timer` lines 5-6.
  `OnUnitActiveSec=30min` with runs of 16-26 minutes leaves gaps of 6-14 minutes.
  Fix: `OnUnitInactiveSec=30min`. Rerun the app's install.sh so the unit is reloaded.

- [x] **1.3 Dialer: "N more" tile does nothing** (S)
  `apps/zorro-dial/zorro-dial` — ring layout about lines 784-791, `activate` about 1156.
  The first ring fits 8 tiles; the rest collapse into an "N more" tile with no action and no
  children. Notes (10 roots) and Messages (9) have unreachable items; deeper rings too.
  Fix: make "N more" a node whose `kids` are the remaining items (paging).
  Check: every root of every part can be reached with mouse and keys.

- [x] **1.4 Dialer: stale pid file kills another process** (S)
  `apps/zorro-dial/zorro-dial` about lines 190-197 and 1207-1209.
  Fix: before sending SIGTERM, check `/proc/<pid>/cmdline` contains `zorro-dial`; else ignore
  and overwrite the pid file.

- [x] **1.5 Face unlock: verify can hang forever** (S)
  `apps/zorro-face/zorro-face` about lines 143-154, 266-274; `apps/zorro-dm/zorro-dm`
  `FaceCheck.run` about 302-306.
  The timeout is only checked when a lit/dark frame pair arrives. With no IR flash no pair
  comes, so the root process and ffmpeg hold the camera and the icon pulses forever.
  Fix: check the deadline on every frame; return "no camera light" when `emitter()` fails
  (its result is ignored now); kill the child from `FaceCheck.run` after about 10 s.

- [x] **1.6 Face unlock: a refused press leaves the icon stuck, wrong messages** (S)
  `apps/zorro-dm/zorro-dm` `look()` about 435-440 and 313; `theme/js/login.js` about 116.
  `look()` returns silently when it refuses; the page has already set `looking` and ignores
  further clicks. Every failure says "face not recognised", also exit codes 2 (not enrolled)
  and 3 (no camera).
  Fix: always answer a refused press with `fail`; map exit codes to their own messages.

- [x] **1.7 update-extras.sh aborts install.sh on a failed download** (S)
  `update-extras.sh` lines 14-20; `install.sh` line 96.
  With `set -euo pipefail` a failed curl or empty grep ends the script before the "No .deb
  found" check, and install.sh stops before stow and the apps.
  Fix: `|| true` on the pipeline so the check runs; in install.sh call it as
  `./update-extras.sh || echo "extras failed, continuing"`.

- [x] **1.8 Settings app: three small bugs** (S)
  `apps/zorro-thinkpad/zsettings/pages_home.py`, `pages_audio.py`.
  a) Volume sliders show the old value after F2/F3 (`pages_home.py` about 216-219,
     `pages_audio.py` about 98-102): `set_value` on the existing slider when not dragged.
  b) The Home "Mobile" pill is always drawn off (`pages_home.py` about 305).
  c) `home_refresh` (about 131-197) has no busy guard and no try/except: slow `netbird
     status` piles up threads, one failing command blanks all six cards. Add a busy flag as
     in `hw_refresh` and a try/except per card.

- [x] **1.9 winpos: terminal reopens in the wrong folder** (S)
  `apps/zorro-winpos/zorro-winpos` about lines 136, 180-200, 220-221.
  The program and folder are read once when the window is first followed. README promises
  the folder the shell was in last.
  Fix: refresh `self.info[wid]` with `self.program(w)` inside `snapshot()`; keep the old
  value when /proc is already gone.

- [x] **1.10 Web-app launchers wipe winpos settings** (S)
  `config/bin/.local/bin/{whatsapp,instagram,linkedin,google-apps}`; winpos writes a block
  to the same `user.js` (`apps/zorro-winpos/zorro-winpos` about 437-443).
  The four scripts are one script copied, and each start overwrites `user.js`.
  Fix: one `zwebapp NAME URL` script; the four become one-line wrappers; edit `user.js`
  between markers instead of overwriting (same pattern as `zsettings/lang.py` `set_firefox`).

- [x] **1.11 Dialer: preview cache never hits** (S)
  `apps/zorro-dial/dialmodes.py` about line 351.
  The cache name uses Python's `hash()`, which changes per process, so thumbnails are
  re-made each open and pile up in `$XDG_RUNTIME_DIR`.
  Fix: `hashlib.sha1(f'{p}|{mtime}|{THUMB}'.encode()).hexdigest()`; prune above 50 files.

- [x] **1.12 Drive watcher: lost events and a stuck folder** (S)
  `apps/zorro-drive/zorro-drive` about lines 349-350, 366-367.
  If `sync_folder` raises in the thread, `running.pop` never runs and that folder is never
  uploaded again. Events during a running sync are dropped.
  Fix: try/finally around the thread body; a "dirty" flag that queues one follow-up sync.

- [x] **1.13 Screenshot clipboard server: dead requestor, leftover temp file** (S)
  `apps/zorro-shot/zorro-shot` `serve_clipboard`.
  python-xlib reports `change_property` errors asynchronously, so the `except` never fires;
  a dead requestor's INCR entry stays in `pending` forever. An X server exit skips the
  temp-file unlink.
  Fix: select `StructureNotifyMask` on the requestor and drop its entries on DestroyNotify;
  a 30 s timeout per transfer; try/finally around the loop for the unlink.

## Phase 2: quick speed wins

- [x] **2.1 Login: the box waits 3.3 s even with the CRT start off** (S)
  `apps/zorro-dm/theme/js/login.js` about line 41 (`appear()`).
  Fix: expose `cfg.crt` on `FX`; wait about 500 ms when it is false.

- [x] **2.2 Dialer: Notes roots rebuilt on every frame** (S)
  `apps/zorro-dial/zorro-dial` about 252, 629-630; `dialmodes.py` about 618-677.
  Each draw (20 per second) calls `part.roots()`; `Notes.roots()` takes 68 ms.
  `search_tiles()` rescans all note text per frame while typing.
  Fix: build roots and tags once at the end of `fetch()`; store lowercased text once; cache
  search results per query string. Measure `roots()` before and after.

- [x] **2.3 Dialer: fetch a part only when first touched** (S)
  `apps/zorro-dial/zorro-dial` about 225-226; `dialmodes.py` about 219-249.
  All five parts are fetched on every open. Add `--rescan no` to the `nmcli` calls.
  Fix: fetch on first hover / click of the hub sector; start eager ones from `GLib.idle_add`
  after the first frame.

- [x] **2.4 Sweep notes: file checks on every frame** (S)
  `apps/zorro-sweep/zorro-sweep` — `draw_score` calls `self.queue()` and `v.to_scan()`
  (about lines 1342, 1361); both `stat` every note (about 2,000) per drawn frame.
  Fix: keep the counts in attributes, recomputed in `next_card()` and after keep / delete /
  send / undo / vault change. `draw_score` only reads them.

- [x] **2.5 Sweep notes: each note read twice at start** (S)
  `apps/zorro-sweep/zorro-sweep` `Vault.__init__` (about 189-198).
  The `rglob` loop reads every `.md` for its links, then `sorted(..., key=self.age)` reads
  the root notes again.
  Fix: in the one loop, keep `when(front(text[:600])[0], p)` in a dict; sort from that.

- [x] **2.6 Settings Home: heavy poll every 5 s, also unfocused** (S-M)
  `apps/zorro-thinkpad/zsettings/pages_home.py` about 91-97, 167-197; `app.py` about 125.
  About 16 processes per round. `printers.installed` 314 ms, `netbird status` 111 ms.
  `nmcli dev wifi` without `--rescan no` triggers Wi-Fi scans.
  Fix: poll only while `self.is_active()`; collect static system info once; printers and
  NetBird every 30 s; add `--rescan no`; refresh Power labels only when that page shows.

- [x] **2.7 Screenshot: faster to the overlay** (S-M)
  `apps/zorro-shot/zorro-shot` about 51-83, 243-275.
  `visible_windows()` runs about 29 xprop / xwininfo processes (0.2 s) before the window
  shows; `import zorro_fx` pulls numpy (90 ms) into every mode, also `--serve` / `--notify`.
  Fix: start `visible_windows()` in a thread first, join at the first motion or click;
  import zorro_fx inside `run_overlay`; cache the dimmed screenshot surface instead of
  painting the full image twice per motion; don't create a cursor per motion event.
  Measure PrtSc → first draw before and after.

- [x] **2.8 Lock screen keeps animating** (S-M)
  `apps/zorro-dm/theme/js/login.js` (no `FX.pause` call), `fx.js` about 861-867,
  `zorro-greeter` about 33-42.
  Fix: after 60 s without input call `FX.pause(true)`, wake on key or mouse; pass a lower
  fps on battery from `look_script()`; let `zorro-lock` pause zorro-wall as it does dunst.

- [x] **2.9 Face unlock: start the camera before loading OpenCV** (S)
  `apps/zorro-face/zorro-face` about 185, 266-269.
  ffmpeg starts after `import cv2` (0.52 s). `conf()` re-reads its file every frame.
  Fix: start `Camera(dev)` right after `emitter()`, then build `Faces()`; read `conf()` once.

- [x] **2.10 zorro_fx: backdrop converted on every frame** (S)
  `apps/zorro-fx/zorro_fx.py` about 487-490.
  Fix: convert the pixbuf once into a cached cairo surface when the backdrop is set.

- [x] **2.11 Search service holds 556 MB (confirm first)** (S-M)
  `apps/zorro-search/zorro-search` about 131-140, 189-231; `zorro-search.service`.
  Expected cause: onnxruntime's memory arena. Not tested.
  Fix to try: `opt.enable_cpu_mem_arena = False`, `opt.enable_mem_pattern = False`; measure
  RSS. If not enough: load the model on first query, drop it after 10 idle minutes. Then
  lower `MemoryHigh`. Also save the index every few hundred pieces, so an interrupted first
  index does not start from zero.

- [x] **2.12 Small per-tick waste** (S each)
  a) Dialer `fan()` re-reads the orb config on every draw and mouse move
     (`zorro-dial` about 434): read once in `__init__`.
  b) Dialer and Sweep `text()` build a new Pango layout per string per frame: cache layouts
     by (text, size, bold, width) as the orb does (`zorro-orb` about 450-469).
  c) Orb wakes every second for a clock that changes once a minute (about 425-438): redraw
     only when the `HH:MM` text changes.
  d) Orb `info_network`: add `--rescan no` (about 105-120).
  e) Drive watcher wakes and stats config.json every second (`zorro-drive` about 327-370):
     add the config folder to inotifywait; block until the next due time.
  f) keyd (`zsettings/lights.py` 118-170, `awake.py` 77-88, `keyd.py` 51-58): one cached
     `camera_or_mic_in_use()` shared by both; `Gio.FileMonitor` instead of the 500 ms poll.
  g) Settings app background at 24 fps while mapped (`app.py` about 107-117): 8-12 fps and
     pause when the window is not active.
  h) Equaliser: each slider change runs `pw-dump` (290 KB of JSON) to find one node id
     (`zsettings/eq.py` about 103-136): cache the id after start.
  i) `fx.js` calls `gl.getAttribLocation` every frame (about 325, 336, 779): cache at init.

- [x] **2.13 install.sh: a rerun repeats heavy steps** (S-M)
  `install.sh` lines 29, 54-81, 96, 166, 224-225; `update-extras.sh`.
  Fix: write repo key / list files only when missing and run the second `apt update` only if
  one changed; guard locale-gen with `locale -a | grep -q en_IE.utf8`; in update-extras
  compare the release `tag_name` with `dpkg-query -W -f='${Version}'` and skip when equal.

## Phase 3: one look, shared helpers

- [x] **3.1 One shared palette and font** (M)
  Colours are defined per app: `apps/zorro-dm/theme/style.css` 2-8, `apps/zorro-fx/
  zorro_fx.py` 53, `zorro-face/faceview.py` 455-519, `zorro-dial/zorro-dial` 34,
  `zorro-sweep/zorro-sweep` (BG, FG, DIM, RED, CYAN, GREEN), `zorro-shot` (blue frame, about
  532-552), `zsettings` (green `#5fd068`, amber `#ffb84a`, grey `#8a8a92` in 10 places).
  Fix: add BG, FG, DIM, RED, CYAN, FONT and one `chroma_text()` (the red / cyan split) to
  `zorro_fx.py`; import them everywhere; a comment in `style.css` pointing at it. Status
  marks: on = cyan, warning = red, off = grey. Screenshot frame and label in cyan and
  DejaVu Sans Mono. Decide the settings app's default font once (`zsettings/windows.py` 16).

- [x] **3.2 One shared helper module next to zorro-fx** (M)
  Done: `apps/zorro-fx/zorro_util.py` (vaults, vault_entries, read_json, write_json) used by
  search, sweep, dial, settings; settings writes made atomic. Left on purpose: the three
  `ago()` give different texts by design, and the `.desktop` readers need different fields.
  Copies today: Obsidian `vaults()` (dialmodes.py 527, zorro-search 41, zorro-sweep 75,
  zsettings/pages_accounts.py 96); atomic JSON write (5+ in drive, winpos, zsettings);
  `ago()` (zorro-drive 427, dialmodes.py 48, zorro-sweep 126); `.desktop` parsing
  (zorro-winpos 368-383, zorro-icons/build-icons 41-54, zorro-winicons 32-51);
  `run` / `spawn` / `sysread` / `load_conf` (dialmodes.py, zorro-orb, zorro-dial,
  zsettings/base.py); Firefox cookie reading twice in zorro-music (neither closes sqlite).
  Fix: one module (for example `apps/zorro-fx/zorro_util.py`) with `vaults()`,
  `read_json`, `write_json` (atomic), `conf_path(app)`, `ago`, `desktop_entries`, `run`,
  `spawn`. Each app's install.sh must keep working alone: import with the same
  `sys.path.insert` pattern used for zorro_fx, and keep a fallback where an app must run
  without it.

- [x] **3.3 Settings app: shared form widgets** (M)
  Done: ui.form / combo / scale / switch / colour (one spacing), ui.in_bg / ui.later, ui.mark.
  Left: one shared device_row for the four device lists.
  `zsettings/pages_desktop.py` (grid 157, 358, 561; combo 48, 133, 583; scale 141, 574),
  `pages_look.py` (196, 207, 221), device rows in `pages_thinkpad.py` 262, 382,
  `pages_audio.py` 116, `pages_network.py` 83; "thread then update UI" six times.
  Fix: `form`, `combo`, `scale`, `switch`, `colour`, `device_row` and one
  `bg(fn, then, busy=)` with try/except in `zsettings/ui.py`. One spacing, one primary
  button style, one word per action ("Check again" vs "Refresh" vs "Scan").

- [ ] **3.4 Settings app: tab order and one home per setting** (M)
  Done: a (Vincent said go, 2026-11-19), d. Open: b, c (offer first).
  `zsettings/app.py` 53-93.
  a) Tabs: Network, Audio, Power, Hardware, Desktop, Look, Accounts. Merge Theme and Login
     screen into "Look", Presets first.
  b) No sidebar heading when it equals the tab name or the section has one page. Desktop in
     three sections: Desktop (Wallpaper, Dialer, Info circle), Windows & text, Effects.
  c) One home per setting: orb text colour (`pages_desktop.py` 85-89 vs 270-275, two
     formats); webcam preview (Home vs Hardware / VLC); sound tests (Audio only); power
     mode applies on change everywhere; icons get their own sub-page.
  d) "Zorro" everywhere instead of "the ThinkPad app" (`keys.py` 192, policy file line 8,
     `base.py` 104); fix the tooltip at `pages_face.py` 44-46; update README.
  Ask Vincent before a) and c): this changes where he finds things.

- [x] **3.5 Login and lock screen arrangement** (S)
  `apps/zorro-dm/theme/style.css`, `theme/js/login.js`, `zorro-greeter` 176.
  a) Lock mode: host label "locked", placeholder "password to unlock" (`lock_hint` is
     passed but never read).
  b) "checking…" after Enter; on failure call `start()` at once and only clear the field
     when the prompt type changes (typed keys are lost in a 900 ms gap now).
  c) One `--edge` margin for clock and power buttons (40/32 vs 32/26 now), one `.caption`
     class, one `--split`; face icon about 40 px with reserved space.

- [x] **3.6 Dialer arrangement** (S-M)
  Done: a, b, d; for c only the hint is kept on screen. Full scaling with one unit `u` is
  still open (needs testing on a small screen / the VM).
  `apps/zorro-dial/zorro-dial`.
  a) Always draw a short label in the first ring (about line 847).
  b) A fixed search line with a caret showing the end of the text, and a per-part hint
     ("type: search notes") (about 503-584).
  c) One unit `u = min(W, H) / 1080` for rings, icons, offsets (about 442, 508, 782, 857,
     916); the hint falls off screens under 960 px high now.
  d) Sleep gets a moon icon; Wi-Fi appears twice with the same icon (`dialmodes.py` 276-294).

- [x] **3.7 Drive arrangement** (S)
  `apps/zorro-drive/zorro-drive` about 654-675, 908-945, 1056-1074.
  Rows: Sync and Open visible, Log / Resync / Remove in a "⋯" menu. Account actions on the
  right pane's heading line; "Remove account…" on the left. Errors in red, syncing in cyan.
  "client ID" everywhere; verb buttons in confirm dialogs.

- [x] **3.8 Screenshot arrangement** (S-M)
  `apps/zorro-shot/zorro-shot`.
  Keys in button labels ("Copy  Ctrl+C", "Save  Enter", "Cancel  Esc"); window click and
  Space select first so Copy works for windows too, double-click and Enter stay the fast
  path; show the size once. Ask Vincent first: it adds one step to "click a window".

- [x] **3.9 Sweep notes arrangement** (S)
  `apps/zorro-sweep/zorro-sweep`.
  "left to scan" shows in the top bar label and in the score bar: keep the score bar, let
  the top label show only deleted / sorted.

## Phase 4: larger jobs

- [x] **4.1 Dialer stays resident** (M)
  Done: app list cached; zorro-dial --daemon from autostart, Super signals it: dial on screen in
  ~0.1 s instead of ~0.3 s (test screen). Not tried in the VM (zvm opens a window on the desktop).
  Every Super press is a cold start of about 275 ms (`zorro-dial` 203-262, 1206-1213).
  Start hidden at login; a second invocation signals it (SIGUSR1) to show / hide; re-read
  apps only when the application folders' mtime changes. Cheaper first step: cache the app
  list as JSON keyed on those mtimes.

- [x] **4.2 Settings app: build tabs lazily** (M-L)
  Done: tabs are built when opened or linked to, the rest one per idle moment after Home shows;
  F9 to Home 0.63 s -> 0.23 s on the test screen. The slow probes wait for their tab.

- [x] **4.4 Split the big files** (M-L)
  Done: dialparts/ package, sweeplib.py, pages_printers.py + pages_bluetooth.py, js/animals.js.
  Left as is: the Dialer's Dial class and the orb's window class (one GTK window each).
  `zorro-dial/zorro-dial` (one 1,000-line class) and `dialmodes.py` → `parts/<name>.py` +
  `draw.py`; `zorro-dm/theme/js/fx.js` (987 lines) → `animals.js`, one `makeProgram`, one
  `makeTexture`; `zorro-sweep/zorro-sweep` (1,600 lines) → vault / files, notebooks
  dialogs, drawing; `zsettings/pages_thinkpad.py` → printers and Bluetooth pages; the orb's
  window class out of `main()`.

- [x] **4.5 Stop hiding errors** (M)
  Dialer `expand()` turns any error into an empty ring (`zorro-dial` 649); MPRIS helpers
  the same (`dialmodes.py` 725-746). Return one tile "could not load: <reason>" and print
  to stderr. Add timeouts to `wmctrl` / `xclip` calls and run tile actions off the main
  thread while input is grabbed (`zorro-dial` 294-301, 1180; `dialmodes.py` 145, 160, 892).

- [x] **4.6 Blocking calls on the GTK thread** (S-M)
  Settings: debounce sliders and text entries by 300 ms, batch the webcam reset as one
  `v4l2-ctl -c a=1,b=2` (`pages_home.py` 452-515, `webcam.py` 55-57), move `nmcli` / `pactl`
  calls to `bg()`. Drive: `systemctl enable --now`, `rclone config dump`, `systemctl
  is-active` through `in_thread()` (`zorro-drive` 735-881).

- [x] **4.7 Dead and stale bits** (S)
  zsettings: `HW_GROUPS` in the wrong class with 5 dead entries (`pages_desktop.py`
  257-260), `load_orb` duplicate (`power.py` 60-70), unused `descs` (`audio.py` 87),
  `Awake.status`, `cpu_max`, `home_data`, `flow()`, the file `lteprobe`.
  dm / face: `hibernate` / `can_hibernate` (`zorro-greeter` 61, 175), `emitter(on=False)`,
  `self.frame` (`faceview.py` 171, 247), `xsessions()` twice with different filters while
  the page always picks openbox.
  Docs: zorro-wall README says 24 fps, code default is 12; orb README says "every 3 s",
  code does 3 s hovered and 15 s otherwise; zorro-thinkpad README still describes a
  "ThinkPad" tab; zorro-drive README says "no polling".

## Checked, leave alone

- winpos daemon: event driven, 0.0 % CPU, 19 MB.
- Orb: 1.4 % CPU, 72 MB.
- Wallpaper: pauses when covered; its memory is the price of WebKit.
- Icon build: no cache, but small.
- install.sh: no blind appends.
