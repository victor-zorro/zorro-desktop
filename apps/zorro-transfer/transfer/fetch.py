"""Fetching over one connection: the file list, then file by file into the staging folder.

The staging folder and everything in it is for this user only (0700 / 0600): keys wait
there. Small files come in batches, big ones alone and continue where they stopped. Every
file is checked against the sender's SHA-256 before it counts: a copy that does not match
is thrown away and fetched again, a few times; then it is noted as failed and the rest goes
on. A file the sender cannot read, or one that cannot be written here, is noted and skipped.

Half-arrived files wait in SESSION.parts next to the staging folder, named by a hash of
their path, so no name of the sender's can collide with them or grow too long."""
import hashlib
import os
import shutil
import time

from . import check, net, state

TRIES = 3                       # fetches of one file before it is given up
BATCH_FILES, BATCH_BYTES = 500, 16 * state.CHUNK
BATCH_MOST = 4 * state.SMALL    # the most the sender puts in a batch for one file
BATCH_CAP = 32 * state.CHUNK    # the most one batch may bring in all
MANIFEST_MOST = 256 << 20       # bytes of the file list (some homes hold half a million files)
ROOM = 200 << 20                # free space left over when everything is here
UNREADABLE = 'could not be read on the other device'
DAMAGED = 'arrived damaged, also when tried again'
CHANGED = 'its size kept changing on the other device'


class NoRoom(Exception):
    """this device does not have the space for what was chosen"""


class SizeChanged(ConnectionError):
    """the sender announced another size than its list: this connection is dropped"""


def create(path, append=False):
    """a file in the staging folder, for this user only"""
    flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if append else os.O_TRUNC)
    return os.fdopen(os.open(path, flags, 0o600), 'ab' if append else 'wb')


def hash_file(path, sha):
    with open(path, 'rb') as fh:
        while chunk := fh.read(state.CHUNK):
            sha.update(chunk)


def gb(n):
    return f'{n / 1e9:.1f} GB'


class Fetch:
    def __init__(self, rcv, t, stage, first=False):
        self.rcv, self.t, self.stage, self.first = rcv, t, stage, first
        self.parts = stage.with_name(stage.name + state.PARTS)
        self.done = self.total = 0
        self.batch, self.again = [], []
        self.meter = state.Meter(self.tell)

    def tell(self, done, current, speed):
        """progress, here and on the sender"""
        self.rcv.save(done=done, current=current, speed=speed)
        net.send_json(self.t, {'op': 'progress', 'done': done, 'total': self.total,
                               'current': current, 'speed': speed})

    def run(self):
        t0 = time.time()
        for d in (self.stage, self.parts):
            state.private_dir(d)
            os.chmod(d, 0o700)
        os.chmod(state.STAGE, 0o700)
        files = self.manifest()
        if self.first:
            files = [f for f in files if f['path'].startswith(('system/', 'generated/accounts'))]
        self.room(files)
        for f in files:
            self.one(f)
        self.flush()
        for f in self.again:                # not in its batch, or damaged there: alone now
            self.big(f)
        if self.first:
            return
        failed = [f'{path}: {why}' for path, why in self.rcv.failed.items()]
        self.rcv.save(done=self.total, current='', speed=0, took=time.time() - t0,
                      failed=failed[:200], failed_count=len(failed))
        try:                                # everything is here, whether or not this arrives
            net.send_json(self.t, {'op': 'finished'})
            net.recv_json(self.t)
        except (OSError, ValueError):
            pass

    def manifest(self):
        """ask for the list; keep only what belongs to the groups we asked for"""
        asked = [g for g in self.rcv.st.get('groups') or [] if isinstance(g, str)]
        net.send_json(self.t, {'op': 'manifest', 'groups': asked})
        reply = net.recv_json(self.t, limit=MANIFEST_MOST)
        if reply.get('ok') is False:
            raise PermissionError(str(reply.get('error', 'the sender refused')))
        files, refused = check.manifest(reply.get('files'), asked)
        self.total = sum(f['size'] for f in files)
        self.rcv.save_files(files)
        self.rcv.save(total=self.total, files_count=len(files), refused=refused)
        return files

    def room(self, files):
        """is there space for what is still to come? NoRoom (with the numbers) when not"""
        need = sum(f['size'] for f in files if not self.here(f))
        free = shutil.disk_usage(self.stage).free
        if need + ROOM > free:
            raise NoRoom(f'not enough room on this device: {gb(need)} still to come, '
                         f'{gb(free)} free. Make room or choose less, then try again.')

    def fail(self, f, why):
        self.rcv.failed[f['path']] = why
        self.done += f['size']

    def here(self, f):
        final = self.stage / f['path']
        try:
            return final.is_file() and not final.is_symlink() and final.stat().st_size == f['size']
        except OSError:
            return False

    def part_of(self, f):
        """the half-arrived copy of a file and its note (which version of the file it is)"""
        name = hashlib.sha256(f['path'].encode(errors='surrogateescape')).hexdigest()[:32]
        return self.parts / f'{name}.part', self.parts / f'{name}.meta'

    def one(self, f):
        """decide how a file comes: it is here already, failed before, in a batch, or alone"""
        if f['path'] in self.rcv.failed or self.here(f):
            self.done += f['size']
            return
        if f['size'] > state.SMALL or self.part_of(f)[1].exists():
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
        sizes = check.sizes(net.recv_json(self.t), len(batch), BATCH_MOST, BATCH_CAP)
        blobs = [None if n < 0 else net.recv_exact(self.t, n) for n in sizes]
        sums = check.hashes(net.recv_json(self.t), len(batch))
        for f, blob, sha in zip(batch, blobs, sums):
            if blob is None or len(blob) != f['size'] or hashlib.sha256(blob).hexdigest() != sha:
                self.again.append(f)        # alone: the sender then says what is wrong
            else:
                self.keep_small(f, blob)
        self.rcv.got += sum(len(b) for b in blobs if b)
        self.meter.at(self.done, batch[-1]['path'])

    def keep_small(self, f, blob):
        tmp = self.part_of(f)[0]
        try:
            final = self.stage / f['path']
            state.private_dir(final.parent)
            with create(tmp) as fh:
                fh.write(blob)
            os.utime(tmp, (f['mtime'], f['mtime']))
            tmp.replace(final)
        except OSError as e:
            tmp.unlink(missing_ok=True)
            return self.fail(f, f'could not be saved here ({e.strerror or e})')
        self.done += f['size']

    def big(self, f):
        """one file alone; a damaged copy is fetched again, TRIES times at most"""
        for _ in range(TRIES):
            result = self.get(f)
            if result != 'damaged':
                break
        if result == 'ok':
            self.done += f['size']
        elif result.startswith('local:'):
            self.fail(f, f'could not be saved here ({result[6:]})')
        else:
            self.fail(f, UNREADABLE if result == 'gone' else DAMAGED)

    def half(self, f, part, meta):
        """how many bytes of this file are here from an earlier try (0: start over)"""
        stamp = f"{f['path']} {f['size']} {f['mtime']}"
        have = part.stat().st_size if part.is_file() else 0
        if have and (not meta.is_file() or meta.read_text() != stamp or have > f['size']):
            have = 0                        # the file changed on the sender meanwhile
        with create(meta) as fh:
            fh.write(stamp.encode(errors='surrogateescape'))
        return have

    def get(self, f):
        """fetch one file into its .part, check it, then give it its name:
        'ok', 'gone' (the sender cannot read it), 'damaged' (the copy did not match) or
        'local: why' (this device cannot keep it)"""
        part, meta = self.part_of(f)
        try:
            have = self.half(f, part, meta)
        except OSError as e:
            return f'local:{e.strerror or e}'
        net.send_json(self.t, {'op': 'get', 'path': f['path'], 'offset': have,
                               'done': self.done + have})
        sha = hashlib.sha256()
        if have:
            hash_file(part, sha)            # what is on disk counts, not what we remember
        self.t.settimeout(net.patience(have))
        answer = check.header(net.recv_json(self.t))
        trouble = None
        if answer is not None:
            size, offset = answer
            self.same_size(f, size)
            if offset not in (0, have):
                raise check.BadPeer(check.ODD + ' (offset)')
            if offset != have:              # the sender starts over: so do we
                have, sha = 0, hashlib.sha256()
            trouble = self.receive(part, have, size, sha, f['path'])
            reply = net.recv_json(self.t)
            good = reply.get('sha256') == sha.hexdigest()
            answer = None if reply.get('unreadable') is True else answer
        self.t.settimeout(net.IDLE)
        meta.unlink(missing_ok=True)
        if trouble or answer is None or not good:
            part.unlink(missing_ok=True)
            return f'local:{trouble}' if trouble else 'gone' if answer is None else 'damaged'
        return self.name_it(f, part)

    def same_size(self, f, size):
        """the sender must send the size of its list; else this connection ends (the next one
        brings a new list), and after TRIES the file is given up"""
        if size == f['size']:
            return
        tries = self.rcv.tries[f['path']] = self.rcv.tries.get(f['path'], 0) + 1
        if tries >= TRIES:
            self.rcv.failed[f['path']] = CHANGED
        raise SizeChanged(f"{f['path']}: the other device sent another size than it listed")

    def name_it(self, f, part):
        final = self.stage / f['path']
        try:
            state.private_dir(final.parent)
            os.utime(part, (f['mtime'], f['mtime']))
            part.replace(final)
        except OSError as e:
            part.unlink(missing_ok=True)
            return f'local:{e.strerror or e}'
        return 'ok'

    def receive(self, part, have, size, sha, rel):
        """the bytes from have to size, into the .part file; what went wrong here (the bytes
        are read to the end all the same, so the connection stays usable), None when nothing"""
        left, trouble, fh = size - have, None, None
        try:
            fh = create(part, append=have > 0)
        except OSError as e:
            trouble = e.strerror or str(e)
        try:
            while left > 0:
                chunk = self.t.recv(min(state.CHUNK, left))
                if not chunk:
                    raise ConnectionError('connection lost')
                trouble = trouble or self.write(fh, chunk)
                sha.update(chunk)
                left -= len(chunk)
                self.rcv.got += len(chunk)
                self.meter.at(self.done + size - left, rel)
        finally:
            if fh:
                fh.close()
        return trouble

    @staticmethod
    def write(fh, chunk):
        """None when it was written, else why not"""
        try:
            fh.write(chunk)
        except OSError as e:
            return e.strerror or str(e)
        return None
