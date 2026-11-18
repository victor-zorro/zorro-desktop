# zorro-dial: the Dialer

The app launcher (called the Dialer): a dial around a clock, in the Chromatic sea look.

- **Three rings**: the apps you start most sit on the inner ring, less used ones further out
  (usage counts with a two-week half-life: `~/.local/state/zorro-dial/usage.json`).
- **Three slices**, each an app category (by the .desktop `Categories`): Work, Media, System
  by default; names, categories and slots per ring in `~/.config/zorro-dial/config.json`
  (Zorro app → Desktop → Launcher).
- **The hub has six parts** (`dialmodes.py`): Apps · Music · Notes · Messages · System ·
  Files. Hover a part: its preview in the centre; click: it stays and the fan shows it
  (click it again or Esc: back to Apps; Super always opens on Apps). The centre of the hub
  runs the kept part's main action (clear all messages, new note, open Nemo).
  - Messages: **a tree** of dunst's history. All, then Signal, WhatsApp, Instagram, Email and
    LinkedIn always in that order (web apps all notify as "Firefox": the site in the text
    decides), other apps, Do not disturb. A source unfolds into its messages, a message into
    Show again / Go to the app / Copy text / Dismiss. The centre of the circle clears all.
  - System: battery / Wi-Fi / CPU / disk, switches (Wi-Fi, Bluetooth, Mobile, Airplane, Do not
    disturb), Lock, Sleep, and Log out / Restart / Power off with a second click to confirm.
  - Files: **a tree**. Places (Home, Downloads, Documents, Pictures, Drive, Recent, bookmarked
    shares, USB, Network) in the first ring; rest the mouse 0.4 s on a folder (or hold Super) and
    its contents unfold in the next ring, beside it; deeper than three levels the tree moves
    inward. Click opens (folders in Nemo), Esc goes one level back, the centre shows the path
    and opens that folder. A mounted share (gvfs) unfolds too. Rest on a **file** and a preview
    panel shows beside the dial: photos (HEIC/WebP through ffmpeg), a video frame and its
    length (ffmpegthumbnailer), a PDF's first page (pdftoppm), audio title/artist/length
    (ffprobe), the first lines of text and code; moving on hides it.
  - Notes: **a tree** of the Obsidian vault. New note, Pinned (Obsidian bookmarks), Recent,
    your folders (after the Evernote move: the notebooks), Tags (inline #tags and the
    frontmatter tags Evernote's import writes). A folder unfolds into subfolders and notes,
    a tag into its notes, a note into its headings (click: open at that heading). Typing
    searches every note, title and text; Enter opens the first.
  - Music: **a tree** (apps/zorro-music, scapi.py). My likes, your top styles (from the
    likes' genres), Discover, your playlists, play a link. A style unfolds into: play my
    likes in it (shuffled), Discover (new tracks in that style), More like these, Top
    artists, your liked tracks. A track unfolds into Play / Play next / Like-Unlike.
    Previous / play-pause / stop / next sit in the centre of the circle; the playing
    track is a white particle band along the outer edge.
- **One gear for all settings apps** in the last slice; Zorro itself stays visible too.
- **Drag to rearrange**: drag an app to another place in its slice, or onto another slice.
  The order is saved (`order` and `assign` in the config); apps you never moved follow
  after, by usage. Zorro app → Launcher → *Reset arrangement* goes back to usage only.
- Type to search all apps, Enter starts the first match, Esc or a click outside closes,
  opening it again closes it.
- Opens with **Super+Space**, and with a **tap of Super** via `xcape` (Super with other keys
  stays Super). Rofi stays on **Super+Shift+Space**.
