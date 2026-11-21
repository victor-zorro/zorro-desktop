"""What the sender does for one paired receiver, request by request.

  offer     the groups with their sizes
  manifest  the file list of the groups asked for; the first one pins the session to those
            groups: a later one may not ask for more
  get       one file, from an offset; after the bytes a SHA-256 of the whole file
  batch     many small files in one go; after the bytes a SHA-256 for each
  progress  the receiver's numbers, so both devices show the same
  finished  the receiver has everything

Only files of the last manifest are served. A file that cannot be opened is answered with
"not here" before any byte is sent, so the receiver skips it and goes on."""
import hashlib
import os
import stat
import time

from . import items, net, state

BATCH_MOST = 4 * state.SMALL    # a small file that grew past this is not sent in a batch


class Serving:
    def __init__(self, sender, t, sid, peer):
        self.sender, self.t, self.sid = sender, t, sid
        self.s = sender.sessions[sid]
        self.allowed = {}
        self.base = 0
        self.meter = state.Meter(self.count)
        self.s.update(status='connected', route=state.route_kind(peer), updated=time.time())

    def count(self, done, current, speed):
        self.s.update(done=done, current=current, speed=speed, updated=time.time())
        self.sender.save('sending')

    def run(self):
        """answer requests until the receiver has everything or the connection ends"""
        self.t.settimeout(net.IDLE)
        self.sender.save('sending')
        ops = {'offer': self.offer, 'manifest': self.manifest, 'get': self.get,
               'batch': self.batch, 'progress': self.progress}
        while True:                         # ends with 'finished' or a lost connection
            req = net.recv_json(self.t)
            if req.get('op') == 'finished':
                return self.finished()
            if req.get('op') in ops:
                ops[req['op']](req)

    def offer(self, _req):
        offer = []
        for gid, (title, about, _paths) in items.all_groups().items():
            fl = items.files(gid)
            offer.append({'id': gid, 'title': title, 'about': about,
                          'files': len(fl), 'bytes': sum(f[1] for f in fl)})
        net.send_json(self.t, {'groups': offer, 'running': items.running(list(items.RUNNING))})

    def manifest(self, req):
        asked = [g for g in req.get('groups') or [] if isinstance(g, str)]
        pinned = self.s.get('groups')
        if pinned is not None and not set(asked) <= set(pinned):
            net.send_json(self.t, {'ok': False, 'error': 'this transfer was started for other parts'})
            return
        fl = file_list(asked)
        self.allowed = {f['path']: f for f in fl}
        self.s.update(groups=asked if pinned is None else pinned, total=sum(f['size'] for f in fl))
        net.send_json(self.t, {'ok': True, 'files': fl})

    def opened(self, rel):
        """the file behind a path of the list, open for reading; None when it cannot be"""
        f = self.allowed.get(rel) if isinstance(rel, str) else None
        if not f or not items.safe_rel(rel):
            return None
        try:                                # O_NONBLOCK: never hang on something odd
            fh = os.fdopen(os.open(items.source(rel), os.O_RDONLY | os.O_NONBLOCK), 'rb')
        except OSError:
            return None
        if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
            fh.close()
            return None
        return fh

    def get(self, req):
        fh = self.opened(req.get('path'))
        if fh is None:
            net.send_json(self.t, {'ok': False})
            return
        with fh:
            st, f = os.fstat(fh.fileno()), self.allowed[req['path']]
            off = req.get('offset', 0)
            same = (st.st_size, max(0, int(st.st_mtime))) == (f['size'], f['mtime'])
            if not isinstance(off, int) or not 0 <= off <= st.st_size or not same:
                off = 0                     # it changed since the list: from the start
            self.t.settimeout(net.patience(off))
            net.send_json(self.t, {'ok': True, 'size': st.st_size, 'offset': off})
            self.base = number(req.get('done')) - off    # the receiver's bytes before this file
            digest = self.stream(fh, st.st_size, off, req['path'])
        net.send_json(self.t, {'sha256': digest})
        self.t.settimeout(net.IDLE)

    def stream(self, fh, size, off, rel):
        """send the bytes from off to size; the SHA-256 of all of them from 0 ('' when the
        file shrank meanwhile: the receiver then throws its copy away)"""
        sha, short, pos = hashlib.sha256(), False, 0
        while pos < size:
            chunk = fh.read(min(state.CHUNK, size - pos))
            if not chunk:
                short = True
                chunk = b'\0' * min(state.CHUNK, size - pos)    # keeps the count; never kept
            sha.update(chunk)
            if pos >= off:
                self.t.sendall(chunk)
            elif pos + len(chunk) > off:
                self.t.sendall(chunk[off - pos:])
            pos += len(chunk)
            if pos > off:
                self.meter.at(self.base + pos, rel)
        return '' if short else sha.hexdigest()

    def small(self, rel):
        """the whole content of a small file, None when it cannot be read"""
        fh = self.opened(rel)
        if fh is None:
            return None
        try:
            with fh:
                data = fh.read(BATCH_MOST + 1)
        except OSError:
            return None
        return data if len(data) <= BATCH_MOST else None

    def batch(self, req):
        paths = (req.get('paths') or [])[:1000]
        blobs = [self.small(rel) for rel in paths]
        net.send_json(self.t, {'sizes': [-1 if b is None else len(b) for b in blobs]})
        for b in blobs:
            if b:
                self.t.sendall(b)
        net.send_json(self.t, {'sha256': ['' if b is None else sha(b) for b in blobs]})
        sent = sum(len(b) for b in blobs if b)
        self.s.update(done=number(req.get('done')) + sent, updated=time.time(),
                      current=str(paths[-1]) if paths else '')
        self.sender.save('sending')

    def progress(self, req):
        self.s.update(done=number(req.get('done')), speed=number(req.get('speed')),
                      total=number(req.get('total')) or self.s.get('total', 0),
                      current=str(req.get('current', ''))[:4096], updated=time.time())
        self.sender.save('sending')

    def finished(self):
        self.s.update(status='done', done=self.s.get('total', 0), updated=time.time())
        self.sender.save('done')
        state.notify('Transfer: everything was sent', f"to {self.s.get('peer', 'the other device')}")
        net.send_json(self.t, {'ok': True})


def sha(data):
    return hashlib.sha256(data).hexdigest()


def number(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0 else 0


def file_list(groups):
    return [{'group': g, 'path': p, 'size': size, 'mtime': mtime, 'mode': mode}
            for g in groups for p, size, mtime, mode in items.files(g)]
