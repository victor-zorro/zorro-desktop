# zorro-wall

The living wallpaper: the login screen's engine (`apps/zorro-dm/theme/js/fx.js`) as the
desktop background, in a WebKit view on a desktop-type window. Iridescent background
(deep sea / waves / light streaks) with the wireframe sea animal and marine snow.

- Follows the login look (`/etc/zorro-dm/look.json`) by default, with the TV effects toned
  down (no CRT start, few glitches, less grain).
- 12 frames a second on the charger, 6 on battery, half resolution; drawing stops while windows cover the
  desktop (X visibility). The background itself is computed at quarter resolution.
- Settings: `~/.config/zorro-wall/config.json`, edited in the Zorro app → Desktop → Wallpaper.
