"""Downloads that can be picked up where they stopped, with a progress line and a sha256 check."""
import hashlib
import sys
import time
import urllib.error
import urllib.request

AGENT = 'zorro-ai/1.0'
TRIES = 5
BLOCK = 1 << 20


class DownloadError(Exception):
    pass


def open_url(url, start=0, timeout=30):
    headers = {'User-Agent': AGENT}
    if start:
        headers['Range'] = f'bytes={start}-'
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout)


def fetch(url, dest, sha256=None, progress=None):
    """Download url to dest through dest.part; a .part left by an earlier run is continued."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + '.part')
    last = None
    for attempt in range(TRIES):
        try:
            _fetch_once(url, part, progress)
            break
        except (OSError, urllib.error.URLError) as e:
            last = e
            time.sleep(min(2 * (attempt + 1), 10))
    else:
        raise DownloadError(f'download failed after {TRIES} tries: {last}')
    if sha256 and file_sha256(part) != sha256:
        part.unlink()
        raise DownloadError(f'{dest.name}: wrong checksum, the download was removed')
    part.replace(dest)
    return dest


def _fetch_once(url, part, progress):
    have = part.stat().st_size if part.exists() else 0
    try:
        resp = open_url(url, have)
    except urllib.error.HTTPError as e:
        if e.code == 416 and have:          # the .part already holds the whole file
            return
        raise
    with resp:
        if have and resp.status != 206:     # the server started over
            have = 0
        total = have + int(resp.headers.get('Content-Length') or 0)
        with open(part, 'ab' if have else 'wb') as out:
            for block in iter(lambda: resp.read(BLOCK), b''):
                out.write(block)
                have += len(block)
                if progress:
                    progress(have, total)
    if total and have < total:
        raise OSError(f'connection closed at {have} of {total} bytes')


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(BLOCK), b''):
            digest.update(block)
    return digest.hexdigest()


def progress_line(name, out=sys.stderr):
    """a progress callback that redraws one line, at most four times a second"""
    state = {'at': 0.0}

    def show(have, total):
        now = time.monotonic()
        if now - state['at'] < 0.25 and have < total:
            return
        state['at'] = now
        pct = f'{100 * have / total:5.1f}%' if total else ''
        end = '\n' if total and have >= total else ''
        out.write(f'\r{name}: {have / 1e6:8.1f} MB {pct}{end}')
        out.flush()
    return show
