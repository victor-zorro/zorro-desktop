"""Where Transfer keeps things, and the small helpers both sides share.

State (sender.json, receiver.json, lock files) lives in ~/.local/state/zorro-transfer, received
files wait in ~/.local/share/zorro-transfer/SESSION. Both folders are for this user only."""
import fcntl
import json
import os
import shutil
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

HOME = Path.home()
STATE = Path(os.environ.get('XDG_STATE_HOME') or HOME / '.local/state') / 'zorro-transfer'
STAGE = Path(os.environ.get('XDG_DATA_HOME') or HOME / '.local/share') / 'zorro-transfer'
CHUNK = 1 << 20
SMALL = 512 << 10               # files up to this size come in batches
RETRY_FOR = 30 * 60             # a lost connection: keep trying this long (seconds)
RETRY_PAUSE = 5                 # between two tries
APPS_WAIT = 24 * 3600           # "by itself" waits this long for apps to be closed
APPS_POLL = 10
STAGE_KEEP = 7 * 24 * 3600      # a staging folder nobody came back to for a week is removed
PARTS = '.parts'                # SESSION.parts: half-arrived files, next to SESSION


class Busy(Exception):
    """another process on this device is doing the same job"""


def write_state(name, data):
    STATE.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE, 0o700)
    tmp = STATE / f'.{name}.{os.getpid()}.tmp'
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as f:
        json.dump(data, f)
    tmp.replace(STATE / name)


def read_state(name, kind=dict):
    try:
        data = json.loads((STATE / name).read_text())
    except (OSError, ValueError, RecursionError):
        return kind()
    return data if isinstance(data, kind) else kind()


def touch(name):
    """a sign with only a time: the user opened Transfer"""
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / name).touch()


def touched(name):
    """when the sign was last left, 0 when never"""
    try:
        return (STATE / name).stat().st_mtime
    except OSError:
        return 0


@contextmanager
def locked(name):
    """hold a lock file while a job runs; Busy when another process holds it"""
    STATE.mkdir(parents=True, exist_ok=True)
    fd = os.open(STATE / name, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Busy('a transfer is already running on this device') from None
        yield
    finally:
        os.close(fd)


def write_pid(name, pid=None):
    """a small file with a process number: a signal for, or a sign of, that process"""
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / name).write_text(str(pid or os.getpid()))


def read_pid(name):
    try:
        return int((STATE / name).read_text().strip())
    except (OSError, ValueError):
        return None


def is_transfer(pid):
    """is this process number a running zorro-transfer?"""
    try:
        return bool(pid) and 'zorro-transfer' in Path(f'/proc/{pid}/cmdline').read_text()
    except OSError:
        return False


def private_dir(d):
    """make a folder and its missing parents, readable by this user only"""
    missing = []
    while not d.is_dir():
        missing.append(d)
        d = d.parent
    for p in reversed(missing):
        p.mkdir(mode=0o700, exist_ok=True)


def clean_stage(keep=None):
    """remove what earlier transfers left waiting (copied keys among it), except one session"""
    if not STAGE.is_dir():
        return
    for d in STAGE.iterdir():
        if d.name not in (keep, f'{keep}{PARTS}') and d.is_dir() and not d.is_symlink():
            shutil.rmtree(d, ignore_errors=True)


def clean_old_stages(current=None, current_seen=0):
    """remove staging folders nobody came back to for STAGE_KEEP; the current session counts
    from its last sign of life"""
    if not STAGE.is_dir():
        return
    now = time.time()
    for d in STAGE.iterdir():
        try:
            seen = d.stat().st_mtime
            if current and d.name in (current, f'{current}{PARTS}'):
                seen = max(seen, current_seen)
            if now - seen > STAGE_KEEP and d.is_dir() and not d.is_symlink():
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            continue


def notify(title, body=''):
    try:
        subprocess.Popen(['notify-send', '-a', 'Transfer', '-i', 'folder-remote', title, body],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def device_name():
    return os.environ.get('ZORRO_TRANSFER_NAME') or socket.gethostname()   # the variable: tests


def route_kind(host):
    """how we reach the other device: 'cable', 'wifi', 'netbird', 'mobile' or ''"""
    try:
        ip = socket.getaddrinfo(host, None)[0][4][0]
        out = json.loads(subprocess.run(['ip', '-j', 'route', 'get', ip], capture_output=True,
                                        text=True, timeout=3).stdout or '[]')
        dev = out[0].get('dev', '') if out else ''
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return ''
    return ('netbird' if dev.startswith('wt') else 'wifi' if dev.startswith('wl') else
            'mobile' if dev.startswith('ww') else 'cable' if dev.startswith(('en', 'eth')) else
            'local' if dev == 'lo' else '')


class Meter:
    """counts bytes and works out the speed; tells at most twice a second"""

    def __init__(self, tell):
        self.tell, self.last, self.mark, self.speed = tell, 0, None, 0

    def at(self, done, current):
        now = time.time()
        if now - self.last < 0.5:
            return
        if self.mark is None:
            self.mark = (now, done)
        dt = now - self.mark[0]
        if dt > 0.4:
            self.speed = (done - self.mark[1]) / dt
        if dt > 3:
            self.mark = (now, done)
        self.last = now
        self.tell(done, current, self.speed)
