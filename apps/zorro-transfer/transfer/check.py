"""What the other device says is checked here, once, when it arrives. Nothing it sends is
used as a path, a number or a name before it passed one of these."""
import re

from . import items

SESSION = re.compile(r'[0-9a-f]{16}')
SECRET = re.compile(r'[0-9a-f]{64}')
ODD = 'the other device sent something this version does not understand'
MOST_FILE = 4 << 40             # bytes in one file (4 TB)
MOST_TOTAL = 16 << 40           # bytes in one transfer
MOST_FILES = 2_000_000          # files in one transfer


class BadPeer(ValueError):
    """the other device broke the rules of the conversation: stop, do not retry"""


def is_session(sid):
    return isinstance(sid, str) and bool(SESSION.fullmatch(sid))


def is_secret(secret):
    return isinstance(secret, str) and bool(SECRET.fullmatch(secret))


def session(reply):
    """the session id and secret a sender hands out after pairing"""
    if not isinstance(reply, dict) or not is_session(reply.get('session')) \
            or not is_secret(reply.get('secret')):
        raise BadPeer(ODD + ' (session)')
    return reply['session'], reply['secret']


def saved(st):
    """a saved receiver state: without its session when that is not a plain id"""
    if not (is_session(st.get('session')) and is_secret(st.get('secret'))):
        for key in ('session', 'secret', 'files'):
            st.pop(key, None)
    return st


def whole(x):
    return isinstance(x, int) and not isinstance(x, bool) and x >= 0


def offer(reply):
    """the groups a sender offers, and which of its apps are open"""
    groups = reply.get('groups') if isinstance(reply, dict) else None
    running = reply.get('running', []) if isinstance(reply, dict) else None
    good = isinstance(groups, list) and isinstance(running, list) and all(
        isinstance(g, dict) and all(isinstance(g.get(k), str) for k in ('id', 'title', 'about'))
        and whole(g.get('files')) and whole(g.get('bytes')) for g in groups)
    if not good or not all(isinstance(r, str) for r in running):
        raise BadPeer(ODD + ' (offer)')
    return groups, running


def entry(f):
    return isinstance(f, dict) and isinstance(f.get('group'), str) \
        and isinstance(f.get('path'), str) and whole(f.get('size')) \
        and f['size'] <= MOST_FILE and whole(f.get('mtime')) and whole(f.get('mode'))


def manifest(files, asked):
    """the file list of a transfer: (the entries we accept, how many we refused).
    An entry is accepted when its group was asked for and its path belongs to that group."""
    if not isinstance(files, list) or len(files) > MOST_FILES or not all(entry(f) for f in files):
        raise BadPeer(ODD + ' (file list)')
    good, seen = [], set()
    for f in files:
        if f['group'] in asked and f['path'] not in seen and items.belongs(f['group'], f['path']):
            seen.add(f['path'])
            good.append({k: f[k] for k in ('group', 'path', 'size', 'mtime', 'mode')})
    if sum(f['size'] for f in good) > MOST_TOTAL:
        raise BadPeer(ODD + ' (file list: too big)')
    return good, len(files) - len(good)


def header(hdr):
    """the answer to 'get': None when the file is gone, else (size, offset)"""
    if not isinstance(hdr, dict):
        raise BadPeer(ODD + ' (file)')
    if hdr.get('ok') is not True:
        return None
    if not whole(hdr.get('size')) or not whole(hdr.get('offset')) or hdr['offset'] > hdr['size']:
        raise BadPeer(ODD + ' (file size)')
    return hdr['size'], hdr['offset']


def sizes(reply, count, limit, total):
    """the answer to 'batch': one size per file (-1: not in this batch), all together at
    most total bytes"""
    got = reply.get('sizes') if isinstance(reply, dict) else None
    if not isinstance(got, list) or len(got) != count or not all(
            isinstance(n, int) and not isinstance(n, bool) and -1 <= n <= limit for n in got) \
            or sum(n for n in got if n > 0) > total:
        raise BadPeer(ODD + ' (batch)')
    return got


def hashes(reply, count):
    got = reply.get('sha256') if isinstance(reply, dict) else None
    if not isinstance(got, list) or len(got) != count:
        raise BadPeer(ODD + ' (checksums)')
    return got
