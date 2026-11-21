"""Fetching over one connection: the file list, then file by file into the staging folder.

The staging folder and everything in it is for this user only (0700 / 0600): keys wait
there. Small files come in batches, big ones alone and continue where they stopped. Every
file is checked against the sender's SHA-256 before it counts: a copy that does not match
is thrown away and fetched again, a few times; then it is noted as failed and the rest goes
on. A file the sender cannot read is noted and skipped."""
import hashlib
import os
import time

from . import check, net, state

TRIES = 3                       # fetches of one file before it is given up
BATCH_FILES, BATCH_BYTES = 500, 16 * state.CHUNK
BATCH_MOST = 4 * state.SMALL    # the most the sender puts in a batch for one file
UNREADABLE = 'could not be read on the other device'
DAMAGED = 'arrived damaged, also when tried again'


def create(path, append=False):
    """a file in the staging folder, for this user only"""
    flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if append else os.O_TRUNC)
    return os.fdopen(os.open(path, flags, 0o600), 'ab' if append else 'wb')


def hash_file(path, sha):
    with open(path, 'rb') as fh:
        while chunk := fh.read(state.CHUNK):
            sha.update(chunk)


class Fetch:
    def __init__(self, rcv, t, stage, first=False):
        self.rcv, self.t, self.stage, self.first = rcv, t, stage, first
        self.done = self.total = 0
        self.batch, self.again, self.failed = [], [], []
        self.meter = state.Meter(self.tell)

    def tell(self, done, current, speed):
        """progress, here and on the sender"""
        self.rcv.save(done=done, current=current, speed=speed)
        net.send_json(self.t, {'op': 'progress', 'done': done, 'total': self.total,
                               'current': current, 'speed': speed})

    def run(self):
        t0 = time.time()
        state.private_dir(self.stage)
        os.chmod(state.STAGE, 0o700)
        os.chmod(self.stage, 0o700)
        files = self.manifest()
        if self.first:
            files = [f for f in files if f['path'].startswith(('system/', 'generated/accounts'))]
        for f in files:
            self.one(f)
        self.flush()
        for f in self.again:                # a batch file that arrived damaged: alone now
            self.big(f)
        if self.first:
            return
        self.rcv.save(done=self.total, current='', speed=0, took=time.time() - t0,
                      failed=self.failed[:200])
        try:                                # everything is here, whether or not this arrives
            net.send_json(self.t, {'op': 'finished'})
            net.recv_json(self.t)
        except (OSError, ValueError):
            pass

    def manifest(self):
        """ask for the list; keep only what belongs to the groups we asked for"""
        asked = [g for g in self.rcv.st.get('groups') or [] if isinstance(g, str)]
        net.send_json(self.t, {'op': 'manifest', 'groups': asked})
        reply = net.recv_json(self.t)
        if reply.get('ok') is False:
            raise PermissionError(str(reply.get('error', 'the sender refused')))
        files, refused = check.manifest(reply.get('files'), asked)
        self.total = sum(f['size'] for f in files)
        self.rcv.save(files=files, total=self.total, refused=refused)
        return files

    def fail(self, f, why):
        self.failed.append(f"{f['path']}: {why}")
        self.done += f['size']

    def here(self, f):
        final = self.stage / f['path']
        return final.is_file() and not final.is_symlink() and final.stat().st_size == f['size']

    def one(self, f):
        """decide how a file comes: it is here already, in a batch, or alone"""
        if self.here(f):
            self.done += f['size']
            return
        half_done = (self.stage / (f['path'] + '.meta')).exists()
        if f['size'] > state.SMALL or half_done:
            self.flush()
            self.big(f)
            return
        self.batch.append(f)
        if len(self.batch) >= BATCH_FILES or sum(x['size'] for x in self.batch) >= BATCH_BYTES:
            self.flush()

    def flush(self):
        """fetch the waiting small files in one request"""
        if not self.batch:
            return
        batch, self.batch = self.batch, []
        net.send_json(self.t, {'op': 'batch', 'paths': [f['path'] for f in batch],
                               'done': self.done})
        sizes = check.sizes(net.recv_json(self.t), len(batch), BATCH_MOST)
        blobs = [None if n < 0 else net.recv_exact(self.t, n) for n in sizes]
        sums = check.hashes(net.recv_json(self.t), len(batch))
        for f, blob, sha in zip(batch, blobs, sums):
            if blob is None:
                self.fail(f, UNREADABLE)
            elif hashlib.sha256(blob).hexdigest() != sha:
                self.again.append(f)
            else:
                self.keep_small(f, blob)
                self.done += f['size']
        self.rcv.got += sum(len(b) for b in blobs if b)
        self.meter.at(self.done, batch[-1]['path'])

    def keep_small(self, f, blob):
        final = self.stage / f['path']
        state.private_dir(final.parent)
        tmp = final.with_name(final.name + '.part')
        with create(tmp) as fh:
            fh.write(blob)
        os.utime(tmp, (f['mtime'], f['mtime']))
        tmp.replace(final)

    def big(self, f):
        """one file alone; a damaged copy is fetched again, TRIES times at most"""
        for _ in range(TRIES):
            result = self.get(f)
            if result != 'damaged':
                break
        if result == 'ok':
            self.done += f['size']
        else:
            self.fail(f, UNREADABLE if result == 'gone' else DAMAGED)

    def half(self, f, part, meta):
        """how many bytes of this file are here from an earlier try (0: start over)"""
        stamp = f"{f['size']} {f['mtime']}"
        have = part.stat().st_size if part.is_file() else 0
        if have and (not meta.is_file() or meta.read_text() != stamp or have > f['size']):
            have = 0                        # the file changed on the sender meanwhile
        with create(meta) as fh:
            fh.write(stamp.encode())
        return have

    def get(self, f):
        """fetch one file into NAME.part, check it, then give it its name:
        'ok', 'gone' (the sender cannot read it) or 'damaged' (the copy did not match)"""
        final = self.stage / f['path']
        part, meta = final.with_name(final.name + '.part'), final.with_name(final.name + '.meta')
        state.private_dir(final.parent)
        have = self.half(f, part, meta)
        net.send_json(self.t, {'op': 'get', 'path': f['path'], 'offset': have,
                               'done': self.done + have})
        sha = hashlib.sha256()
        if have:
            hash_file(part, sha)            # what is on disk counts, not what we remember
        self.t.settimeout(net.patience(have))
        answer = check.header(net.recv_json(self.t))
        if answer is not None:
            size, offset = answer
            if offset not in (0, have):
                raise check.BadPeer(check.ODD + ' (offset)')
            if offset != have:              # the sender starts over: so do we
                have, sha = 0, hashlib.sha256()
            self.receive(part, have, size, sha, f['path'])
            good = net.recv_json(self.t).get('sha256') == sha.hexdigest()
        self.t.settimeout(net.IDLE)
        meta.unlink(missing_ok=True)
        if answer is None or not good:
            part.unlink(missing_ok=True)
            return 'gone' if answer is None else 'damaged'
        os.utime(part, (f['mtime'], f['mtime']))
        part.replace(final)
        return 'ok'

    def receive(self, part, have, size, sha, rel):
        """the bytes from have to size, into the .part file"""
        left = size - have
        with create(part, append=have > 0) as fh:
            while left > 0:
                chunk = self.t.recv(min(state.CHUNK, left))
                if not chunk:
                    raise ConnectionError('connection lost')
                fh.write(chunk)
                sha.update(chunk)
                left -= len(chunk)
                self.rcv.got += len(chunk)
                self.meter.at(self.done + size - left, rel)
