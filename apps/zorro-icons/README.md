# zorro-icons

The icon theme **Zorro-Lucide**: white line icons with a little transparency, from the open
source [Lucide](https://lucide.dev) set (ISC licence, `lucide/LICENSE`, v1.74.0; only the
icons the mapping uses are kept here).

- `mapping.json`: standard icon names (folders, devices, volume, battery, network, edit
  actions, …) and app icons (Firefox → globe, kitty → terminal, VLC → clapperboard, …) →
  Lucide names. Every name also gets a `-symbolic` twin. Anything not mapped falls back to
  Adwaita.
- `build-icons [--opacity 0.5]` writes `~/.local/share/icons/Zorro-Lucide` (install.sh runs
  it; the Zorro app → Desktop → Text & colours sets the transparency) and user copies of
  .desktop files that point at an icon file (Blender).
- GTK uses it through `gtk-icon-theme-name` in `config/gtk`. Google apps and WhatsApp
  (Firefox profiles) get their own icons: `zorro-google` (mail), `zorro-whatsapp`.

`zorro-winicons` (Openbox autostart) gives every window the same icon (`_NET_WM_ICON`), so
Alt+Tab and the window menu show the white Lucide icons too. It waits on X's window-list
change (`xprop -spy`), no polling, and writes the property through libX11.
