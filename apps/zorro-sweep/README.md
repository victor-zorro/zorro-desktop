# zorro-sweep: Sweep notes

Clean up a big Obsidian vault (by default the one called **Notes**) one note at a time.

**Keep or delete.** A note fills the screen, the oldest first. Swipe it **left to keep** or
**right to delete**.

**Sort into notebooks.** The kept notes come back one by one. Drag each one onto where it
belongs:
- another vault;
- a folder in this vault;
- "Stays in Notes";
- "+ New folder".

The notebook closest in meaning lights up as **best match**. It uses the zorro-search index,
and Enter sends the note there.

## How to swipe
- Drag the card with the mouse, or with a finger on the touch screen.
- Or slide two fingers sideways on the touchpad.

| Key | Keep or delete | Sort |
|---|---|---|
| ← / → | keep / delete | |
| 1–9 | | that notebook |
| Enter | | best match |
| Space | skip (comes round again later) | skip |
| O or double-click | open in Obsidian | open in Obsidian |
| Ctrl+Z / Backspace | undo | undo |
| Page Up/Down, scroll | scroll the note | scroll the note |

## What happens to the files
- **Delete** moves the note into the vault's `.trash` folder, which is Obsidian's own trash.
  Pictures and files that only this note uses go with it.
  - Obsidian Sync removes the note from your phone.
  - The laptop keeps it in `.trash` until you empty it.
- **To another vault**, the note's pictures go along into that vault's attachment folder.
  - If another note still uses a picture, it is copied instead of moved.
  - If the name is already taken there, the picture gets a new name and the link in the note
    is changed to match.
- **To a folder** in the same vault, only the note moves; its links keep working.
- **Undo** puts everything back, but only while the app is open.

Your progress (which notes you kept) is saved in `~/.local/state/zorro-sweep/<vault>.json`,
so you can stop at any time and go on later.

```
zorro-sweep                 the vault called Notes (else the biggest)
zorro-sweep --vault PATH    another vault
```

Install: `./install.sh` (user level, no sudo). It puts the app in the Dialer and in rofi as
"Sweep notes".
