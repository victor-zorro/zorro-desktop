"""Music: whichever player plays (MPRIS), and zorro-music for SoundCloud"""
# flake8: noqa: F403,F405 - helpers come from base (and earlier parts)
from .base import *
from .messages import *
from .system import *
from .files import *
from .notes import *


# ---- Music: whichever player plays (MPRIS), and zorro-music for SoundCloud -------------------
MUSIC = APPS / 'zorro-music' / 'zorro-music'


def mpris_players():
    """[(bus name, props)] of the media players on the session bus"""
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        names = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                              'ListNames', None, None, 0, 1000, None).unpack()[0]
    except Exception:                   # noqa: BLE001 - no bus: no players
        return []
    out = []
    for n in names:
        if not n.startswith('org.mpris.MediaPlayer2.'):
            continue
        try:
            props = bus.call_sync(n, '/org/mpris/MediaPlayer2', 'org.freedesktop.DBus.Properties', 'GetAll',
                                  GLib.Variant('(s)', ('org.mpris.MediaPlayer2.Player',)),
                                  None, 0, 500, None).unpack()[0]
            out.append((n, props))
        except Exception:               # noqa: BLE001 - a player that does not answer
            continue
    return out


def mpris_call(name, method):
    try:
        from gi.repository import Gio
        Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
            name, '/org/mpris/MediaPlayer2', 'org.mpris.MediaPlayer2.Player', method, None, None, 0, 2000, None)
    except Exception as e:              # noqa: BLE001 - the player went away: say so in the log
        print(f'zorro-dial: {name} {method}: {e}', file=sys.stderr)


def scapi():
    """the SoundCloud API helper next to zorro-music (None when it is missing)"""
    sys.path.insert(0, str(APPS / 'zorro-music'))
    try:
        import scapi as m
        return m
    except ImportError:
        return None


class Music(Part):
    """a tree: your likes, your styles, discover, playlists; tracks unfold into Play / Play
    next / Like. The player's controls sit in the centre of the circle."""
    key, title = 'music', 'Music'
    tree = True

    def fetch(self):
        try:                            # the sound output tile (dialparts/sound.py)
            from . import sound
            self.sound = sound.node()
        except Exception as e:          # noqa: BLE001 - no sound tile, the rest still works
            print('zorro-dial: sound:', e, file=sys.stderr)
            self.sound = None
        self.fetch_np()
        self.sc = scapi()
        self.likes, self.lists, self.signed_in = [], [], False
        if self.sc:
            try:
                self.likes = self.sc.likes()
                self.signed_in = bool(self.likes) or bool(self.sc.token())
            except Exception as e:      # noqa: BLE001 - offline or SoundCloud changed: public only
                print(f'zorro-dial: soundcloud: {e}', file=sys.stderr)
        self.liked = {t['id'] for t in self.likes}
        self.ready = True

    # -- the player
    def control(self, what):
        np = self.np or {}
        if np.get('player'):
            mpris_call(np['player'], {'toggle': 'PlayPause', 'play': 'Play', 'pause': 'Pause', 'stop': 'Stop',
                                      'next': 'Next', 'prev': 'Previous'}[what])
        else:
            run(str(MUSIC), what)
        time.sleep(0.4)
        self.fetch_np()

    def fetch_np(self):
        players = mpris_players()
        self.np = None
        for name, props in sorted(players, key=lambda p: (p[1].get('PlaybackStatus') != 'Playing', 'mpv' not in p[0])):
            md = props.get('Metadata') or {}
            if not md.get('xesam:title') and props.get('PlaybackStatus') == 'Stopped':
                continue
            artist = md.get('xesam:artist') or ['']
            self.np = {'player': name, 'title': md.get('xesam:title') or 'Playing',
                       'artist': artist[0] if artist else '', 'playing': props.get('PlaybackStatus') == 'Playing',
                       'pos': (props.get('Position') or 0) / 1e6, 'dur': (md.get('mpris:length') or 0) / 1e6,
                       'app': name.split('.')[3].split('_')[0]}
            break
        self.fetched = time.time()

    def position(self):
        np = self.np or {}
        pos = np.get('pos', 0) + ((time.time() - self.fetched) if np.get('playing') else 0)
        return min(pos, np.get('dur') or pos)

    # -- what to play
    def queue(self, tracks, shuffle=False):
        import random
        urls = [t['url'] for t in tracks if t.get('url')]
        if shuffle:
            random.shuffle(urls)
        if urls:
            spawn(str(MUSIC), 'queue', *urls[:200])

    def track_node(self, t):
        liked = t['id'] in self.liked
        return tile('lucide:music', t['title'][:24], t['artist'][:24],
                    lambda: spawn(str(MUSIC), 'play', t['url']), id=f'track:{t["id"]}',
                    kids=lambda: [tile('lucide:play', 'Play', 'now', lambda: spawn(str(MUSIC), 'play', t['url']),
                                       id=f'play:{t["id"]}'),
                                  tile('lucide:skip-forward', 'Play next', 'after this one',
                                       lambda: spawn(str(MUSIC), 'next-up', t['url']), id=f'next:{t["id"]}'),
                                  tile('lucide:star', 'Unlike' if liked else 'Like', 'on SoundCloud',
                                       lambda: self.like(t, not liked), id=f'like:{t["id"]}', keep=True,
                                       lit=liked)])

    def like(self, t, on):
        if self.sc and self.sc.like(t['id'], on):
            (self.liked.add if on else self.liked.discard)(t['id'])

    def tracks_node(self, icon, name, sub, get, id_):
        return tile(icon, name, sub, None, id=id_, kids=lambda: [self.track_node(x) for x in get()])

    def style_kids(self, style):
        mine = [t for t in self.likes if t['style'] == style]
        artists = {}
        for t in mine:
            artists.setdefault(t['artist'], []).append(t)
        top = sorted(artists.items(), key=lambda kv: -len(kv[1]))[:8]
        out = [tile('lucide:play', f'Play my {style}', f'{len(mine)} likes, shuffled',
                    lambda: self.queue(mine, shuffle=True), id=f'playstyle:{style}'),
               self.tracks_node('lucide:globe', 'Discover', f'new {style}',
                                lambda: self.sc.search('', style=style), f'disc:{style}')]
        if mine and self.sc:
            seed = mine[0]
            out.append(self.tracks_node('lucide:radio-tower', 'More like these', f'like {seed["title"][:16]}',
                                        lambda: self.sc.related(seed['id']), f'rel:{style}'))
        if top:
            out.append(tile('lucide:star', 'Top artists', f'{len(top)} artists', None, id=f'artists:{style}',
                            kids=lambda: [self.tracks_node('lucide:music', a[:20], f'{len(ts)} likes',
                                                           lambda ts=ts: ts, f'artist:{style}:{a}') for a, ts in top]))
        return out + [self.track_node(t) for t in mine[:12]]

    def roots(self):
        if not getattr(self, 'ready', False):
            return [tile('lucide:ellipsis', 'Loading…', '', None, id='loading')]
        out = [self.sound] if getattr(self, 'sound', None) else []     # where it plays: first
        if self.likes:
            out.append(tile('lucide:star', 'My likes', f'{len(self.likes)} tracks', None, id='likes',
                            kids=lambda: [tile('lucide:play', 'Play all', 'shuffled',
                                               lambda: self.queue(self.likes, shuffle=True), id='likes:shuffle'),
                                          tile('lucide:list', 'Newest first', '',
                                               lambda: self.queue(self.likes), id='likes:newest')]
                            + [self.track_node(t) for t in self.likes[:14]]))
            for style, n in (self.sc.styles(self.likes, 5) if self.sc else []):
                out.append(tile('lucide:music', style.title()[:16], f'{n} likes', None, id=f'style:{style}',
                                kids=lambda s=style: self.style_kids(s)))
        if self.sc:
            pub = [s for s, _ in self.sc.styles(self.likes, 5)] if self.likes else self.sc.PUBLIC_STYLES
            out.append(tile('lucide:globe', 'Discover', 'new in your styles' if self.likes else 'free tracks',
                            None, id='discover',
                            kids=lambda: [self.tracks_node('lucide:globe', s.title()[:16], 'new tracks',
                                                           lambda s=s: self.sc.search('', style=s),
                                                           f'disc:{s}') for s in pub]))
        if self.signed_in and self.sc:
            out.append(tile('lucide:list', 'Playlists', 'yours', None, id='playlists',
                            kids=lambda: [tile('lucide:list', p['title'][:20], f'{p["count"]} tracks',
                                               lambda u=p['url']: spawn(str(MUSIC), 'play', u),
                                               id=f'pl:{p["url"]}') for p in self.sc.playlists()]))
        out.append(tile('lucide:clipboard-paste', 'Play a link', 'from the clipboard', self.play_clipboard,
                        id='paste'))
        return out

    def rings(self):
        return [self.roots(), [], []]

    def play_clipboard(self):
        url = run('xclip', '-o', '-selection', 'clipboard').strip()
        if url.startswith('http'):
            spawn(str(MUSIC), 'play', url)

    def search(self, text):
        spawn(str(MUSIC), 'play', 'search', text)

    def preview(self):
        np = getattr(self, 'np', None)
        if not np:
            return 'MUSIC', 'SoundCloud', ['nothing playing' if self.ready else '…']
        t = int(self.position())
        d = int(np.get('dur') or 0)
        when = f'{t // 60}:{t % 60:02d}' + (f' / {d // 60}:{d % 60:02d}' if d else '')
        return 'NOW PLAYING' if np['playing'] else 'PAUSED', np['title'][:22], [np['artist'][:26], when]

    def draw_rim(self, dial, cr, cx, cy, rings, a0, a1):
        """the playing track as a thin band of particles just outside the fan; played: white"""
        import math
        import random
        np = getattr(self, 'np', None)
        if not np:
            return
        r = rings[-1][1] + 14
        frac = (self.position() / np['dur']) if np.get('dur') else 0
        rnd = random.Random(hash(np['title']))
        n = 170
        for j in range(n):
            a = math.radians(a0 + (a1 - a0) * j / n)
            amp = 0.3 + 0.7 * abs(math.sin(j * 0.23 + rnd.random()) * math.cos(j * 0.051))
            played = j / n <= frac
            for _ in range(int(2 + amp * 4)):
                rr = r + rnd.uniform(-1, 1) * amp * 7
                cr.set_source_rgba(*((0.97, 0.97, 0.97) if played else (0.62, 0.62, 0.64)),
                                   (0.9 if played else 0.28) * rnd.uniform(0.5, 1))
                cr.rectangle(cx + math.cos(a) * rr, cy + math.sin(a) * rr, 1.5, 1.5)
                cr.fill()
