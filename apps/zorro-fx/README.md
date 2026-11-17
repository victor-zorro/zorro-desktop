# zorro-fx

The lock-screen look for small on-screen overlays: a dark box with moving particles.
Used by the volume/brightness indicator (`zorro-thinkpad keyd`) and the screenshot bar
(`zorro-shot`). Both import `zorro_fx.py` from this folder (found through their own real
path, so nothing to install) and fall back to a plain dark box without it.

Settings (`~/.config/zorro-fx/config.json`, edited in the ThinkPad app → Overlays):
pattern (floating, falling, rising, swirling, twinkling), colour, amount, speed, particle
size, glow, background and level-bar opacity, how long the indicator stays. Running overlays
pick up a change on their next frame.

Particles only move while an overlay is on screen. There is no compositor, so a see-through
background shows a still image of what is behind the box, taken just before it appears.
