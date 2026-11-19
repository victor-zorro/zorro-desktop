# Screenshot (zorro-shot)

Screenshot overlay for the Openbox desktop. The screen is frozen first (menus and tooltips
stay in the shot), then shown dimmed:

- **drag** = region (drag the edges or corners to adjust, drag inside to move)
- **click** = selects the window under the pointer · **Space** = selects the whole screen
- then **Enter** / double-click = save · **Ctrl+C** = copy only · **Esc** / right-click = cancel
- toolbar: Screen / Window / Region · Copy · Save · Cancel

Saved to `~/Pictures/Screenshots/YYYY-MM-DD_HH-MM-SS.png` and copied to the clipboard; the
notification has *Open* and *Show in folder*.

The clipboard holds the picture **and** the file, so Ctrl+V works almost anywhere:
WhatsApp Web, Signal, a browser upload field or page, an image editor, or Thunar (pastes the
file). A small background process (`zorro-shot --serve`, python3-xlib) serves it until
something else is copied. *Copy* without saving keeps a temp file in `$XDG_RUNTIME_DIR/zorro-shot`
until then.

| Key | |
|---|---|
| PrtSc | overlay |
| Alt+PrtSc | active window, no overlay |
| (Fn+PrtSc, star key) | set in the ThinkPad app |

CLI: `zorro-shot [--region | --window | --full]`. Install: `./install.sh` (no sudo).
