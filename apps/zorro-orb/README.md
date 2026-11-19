# zorro-orb

The round info area on the desktop; replaces conky. A circle in a screen corner with
moving particles (zorro-fx profile `orb`, so it has the same look settings as the overlays).

- **Resting display** (default: clock) while the mouse is elsewhere.
- **Four invisible zones**: the quarters of the circle. Move the mouse over one and the
  circle crossfades to that zone's information; click to open the matching app.
- Items: clock, calendar, battery, network (Wi-Fi, IP, NetBird), system (CPU, memory,
  disk, temperature), Drive sync, messages (dunst notifications), sound and screen.
- The window itself is round (X shape), so the desktop shows around it; with "spill" the
  particles drift out in a soft cloud.
- Data is gathered in a thread (every 3 s while a zone is hovered, every 15 s otherwise), so
  slow commands never stop the animation. The clock is redrawn only when its minute changes.

Settings: `~/.config/zorro-orb/config.json` (what and where) and `~/.config/zorro-fx/config.json`
profile `orb` (look), both edited in the Zorro app → Desktop → Info circle.
`zorro-orb --once` prints every item once.
