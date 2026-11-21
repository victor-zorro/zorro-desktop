# zorro-dial: the Dialer

The app launcher (called the Dialer): a dial around a clock, in the Chromatic sea look.

- **Three rings**: the apps you start most sit on the inner ring, less used ones further out
  (usage counts with a two-week half-life: `~/.local/state/zorro-dial/usage.json`).
- **Three slices**, each an app category (by the .desktop `Categories`): Work, Media, System
  by default; names, categories and slots per ring in `~/.config/zorro-dial/config.json`
  (Zorro app → Desktop → Launcher).
- **The hub has six parts** (`dial/parts/`): Apps · Music · Notes · AI · Messages · Files.
  Hover a part: its preview in the centre; click: it stays and the fan shows it (click it
  again or Esc: back to Apps; Super always opens on Apps). The centre of the hub runs the
  kept part's main action (clear all messages, new note, new chat, open Nemo).
  - **The centre** shows the time and the date, and small under them the connection (the
    Wi-Fi's name, Cable, Mobile or Offline) and the battery (percent, charging or plugged in).
  - Music: **a tree** (apps/zorro-music, scapi.py). First **where it plays**: the laptop's own
    output and each Bluetooth speaker or headphone ticked in the Zorro app (System →
    Bluetooth; `music_outputs` in `~/.config/zorro-thinkpad/config.json`). The one in use is
    lit; a connected one is one tap away; a greyed one is not connected: one tap connects it
    (it shows "connecting…", at most half a minute) and plays there. The equaliser follows.
    Then My likes, your top styles (from the likes' genres), Discover, your playlists, play a
    link. A style unfolds into: play my likes in it (shuffled), Discover (new tracks in that
    style), More like these, Top artists, your liked tracks. A track unfolds into Play / Play
    next / Like-Unlike. Previous / play-pause / stop / next sit in the centre of the circle;
    the playing track is a white particle band along the outer edge.
  - Notes: **a tree** of the Obsidian vault. New note, Pinned (Obsidian bookmarks), Recent,
    your folders (after the Evernote move: the notebooks), Tags (inline #tags and the
    frontmatter tags Evernote's import writes). A folder unfolds into subfolders and notes,
    a tag into its notes, a note into its headings (click: open at that heading). Typing
    searches every note, title and text; Enter opens the first.
  - AI: **a chat** with zorro-ai (apps/zorro-ai), in a panel beside the hub. Type a question,
    Enter sends it, the answer comes in as it is written; under each answer a dim line says
    which engine answered, with its note if it has one. Esc stops an answer (the question
    goes back on its line), closing the Dialer does too. It is the same conversation as in
    Intelligence (`~/.local/state/zorro-intel/chat.json`); at most the last 20 messages go to
    the engine, no files. "New chat" (top right of the panel, or the centre of the circle)
    puts the old one away in `chats/`. `ai_view` in the config: `history` (what fits; the
    wheel or Page Up shows older) or `last` (only the last question and answer). When the
    service does not run, one line says so.
  - Messages: **one list** of dunst's history, newest first, after the Do not disturb switch.
    Click a message: it shows again; right-click: dismissed. Rest on it and it unfolds into
    Show again / Go to the app / Copy text / Dismiss. The centre of the circle clears all.
  - Files: **a tree**. Places (Home, Downloads, Documents, Pictures, Drive, Recent, bookmarked
    shares, USB, Network) in the first ring; rest the mouse 0.4 s on a folder (or hold Super) and
    its contents unfold in the next ring, beside it; deeper than three levels the tree moves
    inward. Click opens (folders in Nemo), Esc goes one level back, the centre shows the path
    and opens that folder. A mounted share (gvfs) unfolds too. Rest on a **file** and a preview
    panel shows beside the dial: photos (HEIC/WebP through ffmpeg), a video frame and its
    length (ffmpegthumbnailer), a PDF's first page (pdftoppm), audio title/artist/length
    (ffprobe), the first lines of text and code; moving on hides it.
- **One gear for all settings apps** in the last slice; Zorro itself stays visible too.
- **Drag to rearrange**: drag an app to another place in its slice, or onto another slice.
  The order is saved (`order` and `assign` in the config); apps you never moved follow
  after, by usage. Zorro app → Launcher → *Reset arrangement* goes back to usage only.
- Type to search all apps, Enter starts the first match, Esc or a click outside closes,
  opening it again closes it.
- Opens with **Super+Space**, and with a **tap of Super** via `xcape` (Super with other keys
  stays Super). Rofi stays on **Super+Shift+Space**.

**Stays loaded**: the Openbox autostart runs `zorro-dial --daemon`; a Super press then only
signals it and a fresh dial is on screen in ~0.1 s (without the daemon ~0.3 s; Super still works
without it). After changing the code: log out and in, or `pkill -f 'zorro-dial --daemon'` and
start it again.

**Place and size** (Zorro app → Desktop → Dialer → Place): around the info circle's clock, in
any corner (with its own clock there) or as a full circle in the middle; Dialer size and Icon
size 70-160%.

**Apps you never use**: right-click one, or drag it onto the bin in the top-left corner
(top-right when the Dialer sits there); it leaves the slices, typing still finds it. Zorro app
→ Desktop → Dialer → Apps lists every app with a tick box to bring it back (or take it out).

**Slices**: right-click a slice's name to type a new one (its apps and their order go along);
'+ slice' after the last one adds a new slice (up to six), then drag apps into it.

## The code

`zorro-dial` is a launcher of a few lines; the program is the package `dial/` next to it.

| File | Its job |
|---|---|
| `running.py`, `cli.py` | is a Dialer running (asked before GTK loads); show, close, the daemon |
| `state.py` | what changes at run time, in one place (open window, reads under way, ring sizes) |
| `config.py`, `usage.py` | the settings (checked before use), the start counts |
| `applist.py`, `groups.py` | the installed apps; which app goes into which slice |
| `window.py` | the window, built from the classes below; reads the parts' data in threads |
| `look.py` | palette and font (apps/zorro-fx), text, circles, icons |
| `rings.py`, `draw.py`, `hub.py` | where the dial sits and its sizes; one frame; the hub and its centre |
| `slices.py`, `tiles.py`, `arrange.py` | the apps' slices, apps and tiles on the rings, drag / bin / hold menu |
| `tree.py`, `nodes.py`, `preview.py` | a part's tree ring by ring; the file preview panel |
| `mouse.py`, `keys.py`, `actions.py` | input, and what a click does |
| `chat.py`, `chatfile.py`, `aiclient.py`, `chatview.py` | the AI chat: the conversation, the shared file, the socket, the panel |
| `status.py` | the centre's connection and battery line |
| `parts/` | one file per part (`music.py` with `sound.py` and `player.py`, `notes.py`, `ai.py`, `messages.py`, `files.py` with `filepreview.py`) and `base.py` |

A part's data is read in a thread into a fresh copy that is swapped in when complete; a part
that is being drawn never changes. A read that hangs (a dead network share) gives way to a
new one after 20 seconds.

## Tests

    python3 -m unittest discover apps/zorro-dial/tests     # the logic, no screen needed
    apps/zorro-dial/tests/screens.sh OUT                   # the real window, in a private Xvfb

`screens.sh` never touches your screen, files or running Dialer: it makes a HOME and a runtime
dir of its own, puts fake `nmcli`, `pactl`, `bluetoothctl`, `dunstctl` (tests/fakebin) and a
fake zorro-ai (tests/fake_ai.py) in front, drives the dial through its parts, checks what
happens and saves screenshots to OUT. `ANCHOR=orb`, `AI_VIEW=last`, `NO_AI=1` change the scene.
