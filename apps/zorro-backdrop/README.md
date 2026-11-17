# Backdrop (zorro-backdrop)

Moving desktop background in the style of the zorro lock screen: black deep sea with
slowly sinking "marine snow" at different depths (near flakes larger, brighter, faster).

Light on the battery:
- only the pixels around flakes that moved are redrawn (no full-screen frames);
- 24 frames/s on the charger, 12 on battery (`--fps N` to fix it);
- drawing stops completely while windows cover the whole desktop (X VisibilityNotify).

It is a desktop-type window under everything. Conky therefore runs in its own small black
panel window (`config/conky`), so the background cannot paint over it.

Started from Openbox autostart. Install: `./install.sh` (no sudo).
