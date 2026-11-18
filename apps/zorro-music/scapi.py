"""SoundCloud's own web API, as the website uses it, with your login.

The login is borrowed from the Firefox profile where you are signed in to SoundCloud: the
token is read from that profile's cookies when needed, kept in memory only, and sent only
to SoundCloud. Without a login the public part still works (search, related tracks).
Your likes are cached for 6 hours in ~/.cache/zorro-music/ (titles and links, no token).
"""
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

HOME = Path.home()
CACHE = Path(os.environ.get('XDG_CACHE_HOME', HOME / '.cache')) / 'zorro-music'
API = 'https://api-v2.soundcloud.com'
UA = 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0'
LIKES_TTL = 6 * 3600
PUBLIC_STYLES = ['electronic', 'techno', 'deep house', 'ambient', 'lo-fi', 'jazz']
_token = None


def _get(url, headers=None, method='GET', timeout=20):
    req = urllib.request.Request(url, method=method, headers={'User-Agent': UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode()
    return json.loads(body) if body.strip().startswith(('{', '[')) else body


def client_id():
    """SoundCloud's public app id, as in the website's own scripts (cached for a day)"""
    f = CACHE / 'client_id'
    try:
        if time.time() - f.stat().st_mtime < 86400:
            return f.read_text().strip()
    except OSError:
        pass
    html = _get('https://soundcloud.com/')
    for src in reversed(re.findall(r'<script crossorigin src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"', html)):
        m = re.search(r'client_id\s*:\s*"([0-9a-zA-Z]{32})"', _get(src))
        if m:
            CACHE.mkdir(parents=True, exist_ok=True)
            f.write_text(m.group(1))
            return m.group(1)
    raise RuntimeError('SoundCloud app id not found')


def firefox_profiles():
    return list((HOME / '.local/share').glob('firefox-*')) + list((HOME / '.mozilla/firefox').glob('*'))


def token():
    """the login token from the Firefox profile that has one (memory only)"""
    global _token
    if _token is not None:
        return _token or None
    _token = ''
    for d in firefox_profiles():
        db = d / 'cookies.sqlite'
        if not db.is_file():
            continue
        with tempfile.TemporaryDirectory() as tmp:
            cp = Path(tmp) / 'c.sqlite'
            shutil.copy(db, cp)
            try:
                row = sqlite3.connect(cp).execute(
                    "select value from moz_cookies where host like '%soundcloud.com' and name='oauth_token' "
                    "order by expiry desc").fetchone()
            except sqlite3.Error:
                row = None
        if row:
            _token = row[0]
            break
    return _token or None


def api(path, method='GET', auth=True, **params):
    params['client_id'] = client_id()
    url = f'{API}/{path.lstrip("/")}?{urllib.parse.urlencode(params)}'
    tok = token() if auth else None
    return _get(url, {'Authorization': f'OAuth {tok}'} if tok else {}, method=method)


def me():
    try:
        return api('me') if token() else None
    except urllib.error.HTTPError:
        return None


def style_of(t):
    g = (t.get('genre') or '').strip().lower().replace('&', 'and')
    g = re.sub(r'\s+', ' ', g)
    if not g:
        tags = re.findall(r'"([^"]+)"|(\S+)', t.get('tag_list') or '')
        g = next((a or b for a, b in tags), '').lower()
    return {'electronica/dance': 'electronic', 'dance and edm': 'dance', 'drum and bass': 'drum and bass',
            'hip-hop': 'hip hop', 'hip hop and rap': 'hip hop', 'lofi': 'lo-fi'}.get(g, g)


def track(t):
    """what we keep of a track"""
    return {'id': t.get('id'), 'title': t.get('title') or '', 'artist': (t.get('user') or {}).get('username', ''),
            'url': t.get('permalink_url') or '', 'style': style_of(t), 'duration': (t.get('duration') or 0) / 1000}


def _pages(path, key='collection', pick=None, limit=200, max_items=2000, **params):
    out, nxt = [], None
    while len(out) < max_items:
        r = _get(nxt + ('&' if '?' in nxt else '?') + 'client_id=' + client_id(),
                 {'Authorization': f'OAuth {token()}'} if token() else {}) if nxt else \
            api(path, limit=limit, linked_partitioning=1, **params)
        items = r.get(key, []) if isinstance(r, dict) else []
        out += [pick(x) for x in items if pick(x)] if pick else items
        nxt = r.get('next_href') if isinstance(r, dict) else None
        if not nxt or not items:
            break
    return out


def likes(refresh=False):
    """your liked tracks, newest first (cached for 6 hours)"""
    f = CACHE / 'likes.json'
    try:
        if not refresh and time.time() - f.stat().st_mtime < LIKES_TTL:
            return json.loads(f.read_text())
    except (OSError, ValueError):
        pass
    who = me()
    if not who:
        return []
    out = _pages(f'users/{who["id"]}/track_likes', pick=lambda x: x.get('track') and track(x['track']))
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out))
    return out


def styles(tracks, n=5):
    c = Counter(t['style'] for t in tracks if t['style'])
    return c.most_common(n)


def search(text, style=None, limit=30):
    params = {'q': text or '*', 'limit': limit}
    if style:
        params['filter.genre_or_tag'] = style
    r = api('search/tracks', auth=False, **params)
    return [track(t) for t in r.get('collection', [])]


def related(track_id, limit=20):
    r = api(f'tracks/{track_id}/related', auth=False, limit=limit)
    return [track(t) for t in r.get('collection', [])]


def playlists():
    who = me()
    if not who:
        return []
    r = api(f'users/{who["id"]}/playlists', limit=50)
    return [{'title': p.get('title') or '', 'url': p.get('permalink_url') or '', 'count': p.get('track_count', 0)}
            for p in r.get('collection', [])]


def like(track_id, on=True):
    """like (or unlike) a track as you; also updates the cached likes"""
    who = me()
    if not who:
        return False
    api(f'users/{who["id"]}/track_likes/{track_id}', method='PUT' if on else 'DELETE')
    f = CACHE / 'likes.json'
    try:
        lk = json.loads(f.read_text())
        if not on:
            lk = [t for t in lk if t['id'] != track_id]
            f.write_text(json.dumps(lk))
        else:
            f.unlink()                     # refetched next time, with the new like first
    except (OSError, ValueError):
        pass
    return True
