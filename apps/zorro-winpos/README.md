# zorro-winpos

Windows reopen where you left them. Openbox has no memory for this, so this small helper
(started from Openbox autostart) remembers per app the place, size and maximized state of
its normal windows and puts the app's first window back there when it opens again.

- Per app = WM_CLASS (class, plus the instance when it differs: Firefox profiles such as
  Google apps and WhatsApp are separate apps).
- Leaves alone: dialogs (transient windows), popups, our own desktop pieces (`zorro-*`),
  fullscreen (the normal place is kept), and a second window of an app that is already
  open (Openbox places that one, so it does not land exactly on top).
- New windows open on the desktop you are on, also apps like Firefox that would put a
  window back on the desktop it was last on (`"open_on_current_desktop": false` turns it off).
- After a screen change (no external monitor any more) the window is kept on screen.
- Event driven (X window-list, configure and state events), nothing is polled.

Files: `~/.local/state/zorro-winpos/places.json` (what it remembers; delete it to forget),
`~/.config/zorro-winpos/config.json` with `{"ignore": ["WM_CLASS", ...]}` to skip apps.
Needs `python3-xlib`.
