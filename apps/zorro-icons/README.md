# zorro-icons

The icon theme **Zorro-Lucide**: one look for every icon, all with the same transparency.

- **Apps**: the app's own official icon (hicolor / pixmaps / the .desktop file's icon file),
  turned black and white: greyscale with the contrast stretched so dark parts stay visible
  on the dark desktop. Recognisable, but calm. Apps without an icon file (Google apps and
  WhatsApp, Firefox profiles) use the brand's one-colour logo from `brands/`
  ([Simple Icons](https://simpleicons.org) 11.0.0, CC0; see `brands/NOTICE`).
  Choice in the Zorro app: *official* (default) or *lucide* (white line icons for apps too).
- **Symbols** (folders, devices, volume, battery, network, edit actions, …) and our own
  apps: white line icons from the open source [Lucide](https://lucide.dev) set (ISC licence,
  `lucide/LICENSE`, v1.74.0; only the icons `mapping.json` uses are kept). Every name also
  gets a `-symbolic` twin. Anything not mapped falls back to Adwaita.
- `build-icons [--opacity 0.5] [--style official|lucide]` writes
  `~/.local/share/icons/Zorro-Lucide` (install.sh runs it; without options it uses the
  Zorro app's choices from Desktop → Text & colours) and user copies of .desktop files that
  point at an icon file (Blender). Rerun it after installing a new app.
- GTK uses it through `gtk-icon-theme-name` in `config/gtk`, rofi through its config.

`zorro-winicons` (Openbox autostart) gives every window the same icon (`_NET_WM_ICON`), so
Alt+Tab and the window menu show these icons too. It waits on X's window-list change
(`xprop -spy`), no polling, and writes the property through libX11.
