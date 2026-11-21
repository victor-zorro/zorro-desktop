# Build and design rules

These hold for everything in this repo. `tools/check-rules` checks the build rules;
run it before every commit. CLAUDE.md points here.

## Build rules: code stays split

1. **One file, one job, at most 400 lines.** A file that would pass 400 is split first.
2. **One function, at most 60 lines.** Longer means it does two things: split it.
3. **One page = one file.** A page of an app lives in its own file
   (`pages/<menu>_<page>.py`). A file never holds two pages.
4. **Apps are packages.** The program in `apps/<name>/` is a launcher of a few lines;
   the code is a package next to it, split into: `pages/` (what you see), logic
   (no GTK in it, so it can be tested without a screen), and `cli.py`.
5. **Shared things live once.** Colours, font and common widgets come from
   `apps/zorro-fx` (`zorro_style.py`, the shared ui). Never copy code between apps.
6. **Older code may shrink, never grow.** Files and functions that were over a limit
   when these rules started are listed in `tools/rules-baseline.json`. Their listed
   size is their limit. Adding a feature to one of them means splitting it first.
   After shrinking, run `tools/check-rules --update`.
7. **Each page opens in a test.** Every page is built once in a private test screen
   by the page check; a page that fails to open, or is taller than one screen, fails.
8. **Reviews.** A code review before a build starts and one after it, findings into
   DEVS.

## Design rules: direct, never long

1. **Three steps at most: app → menu → submenu → page.** The menu is always visible;
   a submenu appears when a menu has more than one page. Nothing sits deeper.
2. **A page fits one screen. No scrolling pages.** Measured at the laptop's window
   size. Only a list of things (networks, devices, notes) may scroll, inside its
   own box.
3. **A page has one subject and at most 8 controls.** More than 8, or a second
   subject, becomes a new page in the submenu, not a longer page.
4. **A menu or submenu has at most 7 entries.** More means regrouping.
5. **Changes apply at once.** No Save buttons; a line at the bottom says what
   happened. Things that cannot be undone ask once.
6. **Short words.** A label is at most 4 words, a note at most 2 lines. The name in
   the menu is the title of the page.
7. **One look.** Black, thin lines, the Zorro font and colours from `zorro_style.py`;
   cyan = on, red = warning, dim = off. No other colours or fonts.
8. **Everything is reachable directly.** Every page has an address
   (`app --page menu:page`), so the Dialer and other apps can open it in one step.
