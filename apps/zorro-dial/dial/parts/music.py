"""Music: where it plays (the output picker), whichever player plays (MPRIS), and zorro-music
for SoundCloud."""
import copy
import math
import random
import sys
import time

from .. import config
from . import player, sound
from .base import APPS, Part, loading, run, spawn, tile

MUSIC = APPS / 'zorro-music' / 'zorro-music'
CALLS = {'toggle': 'PlayPause', 'play': 'Play', 'pause': 'Pause', 'stop': 'Stop',
         'next': 'Next', 'prev': 'Previous'}


def scapi():
    """the SoundCloud API helper next to zorro-music (None when it is missing)"""
    try:
        import scapi as m
        return m
    except ImportError:
        return None


class Music(Part):
    """a tree: the outputs first, then your likes, your styles, discover, playlists; tracks
    unfold into Play / Play next / Like. The player's controls sit in the centre of the circle."""
    key, title = 'music', 'Music'

    def fetch(self):
        self.read_sound()
        self.read_player()
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

    def renewed(self):
        """the outputs and the player read again; the likes stay (SoundCloud is slow)"""
        if not self.ready:
            return super().renewed()
        fresh = copy.copy(self)
        fresh.read_sound()
        fresh.read_player()
        return fresh

    def read_sound(self):
        self.ticked, self.outs, self.bt = [], [], {}
        try:
            self.ticked = config.music_outputs()
            self.outs = sound.outputs()
            self.bt = sound.bt_devices(self.ticked)
        except Exception as e:          # noqa: BLE001 - no output tiles, the rest still works
            print('zorro-dial: sound:', e, file=sys.stderr)

    def read_player(self):
        self.np = player.now_playing()
        self.fetched = time.time()

    def control(self, what):
        """a player button; the dial reads the new state after it (renewed)"""
        np = self.np or {}
        if np.get('player'):
            player.mpris_call(np['player'], CALLS[what])
        else:
            run(str(MUSIC), what)
        time.sleep(0.4)

    def position(self):
        np = self.np or {}
        pos = np.get('pos', 0) + ((time.time() - self.fetched) if np.get('playing') else 0)
        return min(pos, np.get('dur') or pos)

    # -- what to play
    def queue(self, tracks, shuffle=False):
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

    def likes_tiles(self):
        out = [tile('lucide:star', 'My likes', f'{len(self.likes)} tracks', None, id='likes',
                    kids=lambda: [tile('lucide:play', 'Play all', 'shuffled',
                                       lambda: self.queue(self.likes, shuffle=True), id='likes:shuffle'),
                                  tile('lucide:list', 'Newest first', '',
                                       lambda: self.queue(self.likes), id='likes:newest')]
                    + [self.track_node(t) for t in self.likes[:14]])]
        for style, n in (self.sc.styles(self.likes, 5) if self.sc else []):
            out.append(tile('lucide:music', style.title()[:16], f'{n} likes', None, id=f'style:{style}',
                            kids=lambda s=style: self.style_kids(s)))
        return out

    def roots(self):
        if not self.ready:
            return loading()
        out = sound.tiles(self.outs, self.ticked, self.bt)      # where it plays: first
        if self.likes:
            out += self.likes_tiles()
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

    def play_clipboard(self):
        url = run('xclip', '-o', '-selection', 'clipboard').strip()
        if url.startswith('http'):
            spawn(str(MUSIC), 'play', url)

    def search(self, text):
        spawn(str(MUSIC), 'play', 'search', text)

    def preview(self):
        np = self.np
        if not np:
            return 'MUSIC', 'SoundCloud', ['nothing playing' if self.ready else '…']
        t = int(self.position())
        d = int(np.get('dur') or 0)
        when = f'{t // 60}:{t % 60:02d}' + (f' / {d // 60}:{d % 60:02d}' if d else '')
        return 'NOW PLAYING' if np['playing'] else 'PAUSED', np['title'][:22], [np['artist'][:26], when]

    def draw_rim(self, dial, cr, cx, cy, rings, a0, a1):
        """the playing track as a thin band of particles just outside the fan; played: white"""
        np = self.np
        if not np:
            return
        u = getattr(dial, 'u', 1.0)
        r = rings[-1][1] + 14 * u
        frac = (self.position() / np['dur']) if np.get('dur') else 0
        rnd = random.Random(hash(np['title']))
        n = 170
        for j in range(n):
            a = math.radians(a0 + (a1 - a0) * j / n)
            amp = 0.3 + 0.7 * abs(math.sin(j * 0.23 + rnd.random()) * math.cos(j * 0.051))
            played = j / n <= frac
            for _ in range(int(2 + amp * 4)):
                rr = r + rnd.uniform(-1, 1) * amp * 7 * u
                cr.set_source_rgba(*((0.97, 0.97, 0.97) if played else (0.62, 0.62, 0.64)),
                                   (0.9 if played else 0.28) * rnd.uniform(0.5, 1))
                cr.rectangle(cx + math.cos(a) * rr, cy + math.sin(a) * rr, 1.5, 1.5)
                cr.fill()
