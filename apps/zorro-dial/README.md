# zorro-dial

The app launcher: a dial around a clock, in the Chromatic sea look.

- **Three rings**: the apps you start most sit on the inner ring, less used ones further out
  (usage counts with a two-week half-life: `~/.local/state/zorro-dial/usage.json`).
- **Three slices**, each an app category (by the .desktop `Categories`): Work, Media, System
  by default; names, categories and slots per ring in `~/.config/zorro-dial/config.json`
  (Zorro app → Desktop → Launcher).
- **The hub is the info circle**: its four hidden zones (battery, network, Drive, messages;
  chosen in Zorro app → Info circle) work in the dial's centre too: hover a quarter to see
  it, click to open what the info circle opens.
- **Drag to rearrange**: drag an app to another place in its slice, or onto another slice.
  The order is saved (`order` and `assign` in the config); apps you never moved follow
  after, by usage. Zorro app → Launcher → *Reset arrangement* goes back to usage only.
- Type to search all apps, Enter starts the first match, Esc or a click outside closes,
  opening it again closes it.
- Opens with **Super+Space**, and with a **tap of Super** via `xcape` (Super with other keys
  stays Super). Rofi stays on **Super+Shift+Space**.
