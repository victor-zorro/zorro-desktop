# ThinkPad (zorro-thinkpad)

ThinkPad T14 (Gen 1 AMD) under Openbox: every Fn key works and shows a small indicator at
the bottom centre of the screen. The app is called **Zorro** (F9, rofi "Zorro", `zorro-settings`). It opens on **Home**
(cards for sound, camera, printer, network, power, system); the gear shows the tabs **Network**,
**Audio**, **Power**, **Hardware**, **Desktop** (wallpaper, Dialer, info circle, overlays, windows,
languages, this app), **Look** (theme presets like Chromatic sea for login, lock screen and
wallpaper together, plus your own; every login / lock screen effect; face unlock) and
**Accounts**. The ThinkPad-specific pages:

- **Keys**: what each Fn key does, and what the star key (F12 ★) does.
- **Power**: power mode on charger / battery (TLP platform profile), charge limit
  (80% for long battery life, or 100%), "charge to 100% once", battery health.
- **Lights**: red dot on the lid: a normal pattern (on, off, heartbeat, slow / fast blink,
  double flash, charging, charger only, disk, Morse code with your own text) plus activity
  overrides with their own pattern (message arrives, webcam or mic in use, battery low,
  battery full, on the charger; the highest active one wins). Power button light, keyboard
  light. keyd runs the dot and re-applies everything at login and after standby.
- **Overlays**: particles in the indicator and the screenshot bar (`apps/zorro-fx`),
  with a live preview; optionally the app window gets the same background.
- **Languages** (Desktop): spell checking in several languages at once (English, Dutch,
  German, French, Spanish, Italian, Portuguese), so mixed sentences get no red lines. Apply
  adds / removes the hunspell dictionaries (`zorro-lang-helper`, asks a password) and sets
  Firefox (a block in every profile's user.js, the web apps too) and Obsidian (its
  Preferences, while it is closed). `python3 -m zsettings.lang apply` sets it again.
- **Face unlock** (Look tab): `apps/zorro-face` — learn, test, delete, where the icon shows.

- **Hardware**: every device with ✓ / ⚠, driver and a test: webcam preview (VLC), mic
  mute + record-and-play-back test, speaker left/right test, Bluetooth on/off, connect /
  disconnect / forget, scan & pair, Wi-Fi, LTE modem, printer (CUPS), touchscreen,
  touchpad, fingerprint reader (with the BIOS hint when none is found).

Still to come: LTE + SMS, fingerprint login.

Settings: `~/.config/zorro-thinkpad/config.json` (star key, lights) and
`/etc/tlp.d/20-zorro-thinkpad.conf` (power; written by the root helper through pkexec).

## Keys

| Key | Does | Arrives via |
|---|---|---|
| F1 / F2 / F3 | mute / volume down / up (up also unmutes) | X → Openbox |
| F4 | microphone on/off (LED follows) | keyd |
| F5 / F6 | brightness (finer steps when dark) | X → Openbox |
| F7 | external screen: extend → mirror → external only → laptop only | X → Openbox |
| F8 | airplane mode: all radios off / on | X → Openbox |
| F9 | open the Zorro app | keyd |
| F10 / F11 | mobile data (LTE) on / off | keyd |
| F12 ★ | your choice (default: screenshot) | X → Openbox |
| Fn+Space | keyboard light off/low/high (firmware); indicator shows the level | keyd |
| Fn+PrtSc ✂ | screenshot of an area (`zorro-shot --region`) | keyd |

F4, F9, F10, F11 and Fn+PrtSc send key codes above 255, which X11 cannot deliver.
`zorro-thinkpad keyd` (started from Openbox autostart) reads them straight from the
"ThinkPad Extra Buttons" input device; a udev rule lets the logged-in user read **only that
device**, not the keyboard. keyd also owns the indicator window, so each key press is just
a tiny `zorro-thinkpad key NAME` that sends one message over a unix socket.

`./keytest` (sudo) shows which device and code each special key sends.

## Files

| File | What |
|---|---|
| `zorro-thinkpad` | entry point (also linked as `zorro-settings`); the code is in `zsettings/` |
| `zsettings/cli.py` | command line: `key`, `keyd`, `osd`, `morse`, `--page`, `--apply-windows` |
| `zsettings/base.py` | settings file (atomic, locked writes), small helpers, indicator client |
| `zsettings/keys.py`, `lights.py`, `keyd.py` | Fn key actions; red dot, LEDs, Morse; the background part |
| `zsettings/awake.py` | no screen saver / lock during calls (camera or mic in use) and when apps ask (org.freedesktop.ScreenSaver) |
| `zsettings/power.py`, `hardware.py` | TLP + battery; hardware check rows |
| `zsettings/printers.py` | printers: installed list, network search (Bonjour + SNMP), add by address, driver choice (driverless, else a matching open-source driver) |
| `zsettings/pages_home.py` | Home (opens first): sound + equaliser, webcam, printer, connections, power, system info; the gear opens all setup |
| `zsettings/eq.py` | 10-band equaliser: a small PipeWire filter-chain in front of one output, per-output gains, restored at login |
| `zsettings/webcam.py`, `sysinfo.py` | webcam picture controls (v4l2-ctl; kept settings restored at login and after standby); hardware and usage overview |
| `zsettings/audio.py`, `pages_audio.py` | Audio tab: outputs/inputs (use, volume, mute), per-app output, 'Together' (several outputs at once, restored at login by keyd) |
| `zsettings/pages_network.py` | Network tab: Wi-Fi, Ethernet (libnm), NetBird |
| `zsettings/pages_mobile.py` | Mobile tab: modem status, SIM PIN, mobile data (zorro-lte through pkexec; root-owned copy in /usr/local/lib/zorro-lte) |
| `zorro-lte` | the XMM7360 LTE modem: wake + FCC unlock (xmm7360/ RPC), reset, PIN, up/down, state (JSON) |
| `zsettings/windows.py`, `look.py` | window theme, picom, kitty, GTK css; login look + presets |
| `zsettings/fxshim.py` | loads the shared overlay look (apps/zorro-fx) with a plain fallback |
| `zsettings/app.py`, `ui.py`, `pages_*.py` | the Zorro app: window, shared widgets, one module per tab group |
| `zorro-thinkpad-helper` | root helper, fixed verbs only (`power`, `fullcharge`); installed as a root-owned copy |
| `org.zorro.thinkpad.policy` | polkit: the active local session may run the helper without a password |
| `70-zorro-thinkpad.rules` | udev: brightness + ThinkPad LEDs (level, blink mode) writable for group video, Extra Buttons readable |
| `install.sh` | system part (sudo): udev rule, LED blink modules, helper + polkit |
| `install-user.sh` | user part: links into ~/.local |
| `keytest` | key code tester |

`lteprobe` (in this folder, run with sudo) asks the built-in XMM7360 LTE modem a few
read-only questions and writes the answers to `/tmp/zorro-lteprobe.log`: a diagnostic, changes nothing.
