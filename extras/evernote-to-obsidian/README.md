# Evernote → Obsidian (one-off move, ~1000 notes)

1. Tools (once): `sudo apt install pipx` then `pipx install evernote-backup`
   (open source: fetches every notebook through your own Evernote account).
2. Fetch everything (asks your Evernote login; nothing leaves the laptop otherwise):

       mkdir -p ~/Evernote-export && cd ~/Evernote-export
       evernote-backup init-db        # log in (opens Evernote's login)
       evernote-backup sync           # downloads all notes + attachments
       evernote-backup export enex/   # one .enex file per notebook

3. **Automatic, one vault per notebook** (Zorro app → Accounts → Obsidian → "Moving from
   Evernote"): tick the notebooks, name their vaults, "Make the vaults". Or by hand:

       extras/evernote-to-obsidian/evernote-to-vaults --list
       extras/evernote-to-obsidian/evernote-to-vaults --map "victor-zorro's notebook=Notes" --skip Work

   Each notebook → `~/Notes/<vault>/`, attachments in `_attachments/`, created / updated /
   tags / source in the note's properties, added to Obsidian's vault list (close Obsidian
   first). Rerun-safe: new and changed Evernote notes come in, notes edited in Obsidian stay.

   Or with Obsidian's own Importer, into one vault: create the vault `~/Notes`, then
   Settings → Community plugins → turn them on → Browse → **Importer** (official) →
   "Evernote (.enex)" → pick all files in `~/Evernote-export/enex/` → Import.
   Notebooks become folders, tags stay, images and PDFs become attachments, the original
   dates go into each note's properties.
4. Check: note count per notebook (Importer shows it), a few web clippings, tables and
   checklists. Encrypted Evernote notes cannot be converted: open those in Evernote first.
5. Sync: Settings → Sync (Obsidian Sync) → create a remote vault with your own encryption
   password → connect. On the Android phone: Obsidian app → Sync → the same vault.
6. Keep `~/Evernote-export` until everything is checked; then cancel Evernote.
