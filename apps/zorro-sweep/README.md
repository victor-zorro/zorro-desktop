# zorro-sweep: Sweep notes

Clean up a big Obsidian vault (by default the one called **Notes**) one note at a time.

It plays in **rounds**:
1. **Keep or delete.** A note fills the screen, the oldest first. Swipe it **left to keep** or
   **right to delete**. Ten dots at the top fill up with each note you keep.
2. **Sort.** After **10 kept notes**, "ROUND n" flashes and those 10 come back one by one. Drag
   each one onto where it belongs:
   - another vault;
   - a folder in this vault;
   - "Stays in Notes";
   - "+ New folder".

   The notebook closest in meaning lights up as **best match**. It uses the zorro-search
   index, and Enter sends the note there. Each tile shows how many notes that notebook
   already holds.
3. "ROUND n DONE", and the next 10.

The top of the screen shows:
- the round;
- the dots for the round;
- how many notes are still **to scan**, with a bar for how much of the vault is done.

The picker at the top right chooses **which vault** to sweep, and shows how many notes each one
still has to scan. Deletes don't count toward the 10; only kept notes do.

The two buttons at the top left switch by hand, for example to sort a half-full round.

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
| Ctrl+Z / Backspace, or the undo button under the card | undo | undo |
| Page Up/Down, scroll | scroll the note | scroll the note |

## Undo
The **undo** button under the card shows what it takes back (for example "kept · Mobile Unit
TODO"). The card then flies back from where it went. You can undo step by step, for as long as
the app is open. Notebook changes can be undone too.

## Notebooks
Open the **Notebooks** button at the top right, or right-click a notebook tile in Sort.

- **New notebook**: a new folder in the vault you are sweeping.
- **Rename**:
  - A folder: Obsidian Sync takes the new name online.
  - A vault: Obsidian must be closed, because it keeps its own list of vaults. The online copy
    keeps its old name.
- **Delete a folder**: its notes go back to be swept again, or to the vault's `.trash` folder.
  Obsidian Sync removes the folder online and from your phone. Undo brings it all back.
- **Delete a vault**: you choose what to delete it from:
  - this laptop (to the Trash, where you can still get it back);
  - Obsidian's list of vaults (Obsidian must be closed);
  - online.

  Obsidian has no way for other apps to delete the online copy. The app shows the three clicks
  to do it in Obsidian (Settings → Sync → Manage → trash icon) and how to remove it from your
  phone.

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
