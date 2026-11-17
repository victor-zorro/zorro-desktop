# ThinkPad (zorro-thinkpad)

ThinkPad T14 (Gen 1 AMD) under Openbox: every Fn key works and shows a small indicator at
the bottom centre of the screen. Later steps add the settings app: power modes, lid LED,
keyboard light, LTE + SMS and a hardware check.

## Keys

| Key | Does | Arrives via |
|---|---|---|
| F1 / F2 / F3 | mute / volume down / up (up also unmutes) | X → Openbox |
| F4 | microphone on/off (LED follows) | keyd |
| F5 / F6 | brightness (finer steps when dark) | X → Openbox |
| F7 | external screen: extend → mirror → external only → laptop only | X → Openbox |
| F8 | airplane mode: all radios off / on | X → Openbox |
| F9 | open the ThinkPad app | keyd |
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
| `zorro-thinkpad` | key actions, `keyd`, indicator, (later) the app |
| `70-zorro-thinkpad.rules` | udev: brightness + ThinkPad LEDs writable for group video, Extra Buttons readable |
| `install.sh` | system part (sudo): the udev rule |
| `install-user.sh` | user part: links into ~/.local |
| `keytest` | key code tester |
