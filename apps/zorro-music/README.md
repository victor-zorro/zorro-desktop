# zorro-music

SoundCloud (and any link yt-dlp knows) through one small mpv in the background; the Dialer's
**Music** part is its face.

- **Logged in** without a password here: yt-dlp borrows your SoundCloud login from the
  Firefox profile where you are signed in (`--cookies-from-browser`; found automatically by
  the presence of SoundCloud's login cookie). Your likes and playlists play, in Go+ quality
  when your subscription has it. **Not logged in**: public free tracks.
- mpv with **mpv-mpris** is a normal media player for the desktop: media keys, the Dialer
  (Music part), the Audio tab (per-app output) all see it.
- `zorro-music play URL | likes | search TEXT | fav NAME`, `toggle | next | prev | stop`,
  `status` (JSON).
- Settings `~/.config/zorro-music/config.json`:
  `{"user": "your-soundcloud-name", "favourites": [{"name": "Morning", "url": "https://soundcloud.com/..."}], "volume": 80}`

In the Dialer (Super → the music part of the circle): the track as a particle band (the
played part lit), previous / play-pause / next, your likes, favourites, "play a link" from
the clipboard; typing searches SoundCloud, Enter plays. It controls whichever player
plays (also Firefox or a Bluetooth device), and zorro-music for SoundCloud.

Why not a hidden SoundCloud web page: tested, it needs real clicks (autoplay rules, the
cookie banner) and breaks with every redesign; yt-dlp is lighter and kept up to date.
