# zorro-sweep: Sweep notes

Clean up a big Obsidian vault (by default the one called **Notes**) one note at a time.

It plays in **rounds**:
1. **Keep or delete.** A note fills the screen, the oldest first. Swipe it **left to keep** or
   **right to delete**. Ten dots at the top fill up with each note you keep.
2. **Sort.** After **10 kept notes**, "ROUND n" flashes and those 10 come back one by one. Drag
   each one onto where it belongs (a picked-up card shrinks, so the notebooks stay in view):
   - another vault;
   - a folder in this vault;
   - "Stays in Notes";
   - "+ New folder".

   The notebook closest in meaning lights up as **best match**. It uses the zorro-search
   index, and Enter sends the note there. Each tile shows how many notes that notebook
   already holds. The notebooks lie scattered beside the card, each in its own form
   (circle, hexagon, blob…), bigger when it holds more notes.
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
| + / − / 0, Ctrl+scroll, pinch | zoom the note in / out / back | zoom |

A short note gets bigger letters, and pictures fill the room the text leaves.

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

## Inside Obsidian (laptop and phone)
`obsidian-plugin/` is Sweep as an Obsidian plugin: plain JavaScript (`main.js`, `styles.css`,
`manifest.json`), no build step. `install.sh` copies it into every vault and switches it on in
`community-plugins.json`. Obsidian Sync takes it to the phone.

Once per device:
1. Open the vault. Obsidian asks "Do you trust the author of this vault?": choose **Trust
   author and enable plugins**. On the phone: Settings → Community plugins → Turn on.
2. Settings → Sync → turn on **Installed community plugins** (and **Active community plugin
   list**). Do it on the laptop and the phone.

Then the **brush button** in the ribbon (or the command "Sweep notes: Open") opens it.
- **Start screen**: choose the **vault** (another vault opens it, with Sweep on top) and the
  **notebook to clean up**: the loose notes at the top of the vault, or one of its folders.
- **Keep or delete**: swipe the card left to keep, right to delete (laptop: ← / →).
  Deleted notes, and pictures only they use, go to the vault's `.trash` folder.
- **Sort**: after 10 kept notes, drag each one onto a notebook, or tap a notebook (laptop: 1–9).
  The notebooks are the folders of this vault, plus "Stays in …" and "+ New folder". Moving a note
  to another vault isn't possible here (a plugin only sees its own vault); the laptop app does it.
- **Best match**: the notebook closest in meaning to the note is lit up ("best match"); tap it,
  or press Enter. `zorro-sweep-presort` works these out on the laptop from the zorro-search
  index and writes them into the plugin's data (`suggest`), so the phone gets them through Sync.
  zorro-search runs it after every index update. Only folders of the same vault.
- Undo under the card, two-finger pinch or Ctrl+scroll to zoom, double-tap to open the note.

**Progress is shared.** The plugin keeps it in `.obsidian/plugins/zorro-sweep/data.json`, which
Sync carries along. The laptop app reads and writes that same file when the plugin is in the
vault, so the phone, Obsidian and the laptop app all continue where you left off. (The old
progress in `~/.local/state/zorro-sweep/` is taken over once.) Keys are paths relative to the
vault: `note.md` for loose notes, `Folder/note.md` for notes in a folder.

After changing the plugin: rerun `install.sh` and reload Obsidian (or turn the plugin off/on).
