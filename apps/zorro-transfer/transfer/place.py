"""Putting what was received into place, in the home folder.

What a file replaces stays next to it as NAME.before-transfer. Left alone (counted as kept):
a path that is a symbolic link or lies behind one (set up by this device's own install, for
example ~/.config/openbox into the repo), and anything that is not a plain file. Each file
gets the sender's permissions, without setuid, setgid or "writable by everyone"; logins and
keys are for this user only. A file that cannot be placed is noted; the rest goes on. Files
that run by themselves at login (autostart, ~/bin…) are named in the notes."""
import os
import shutil
import time

from . import after, check, items, state

BACKUP = '.before-transfer'


class AppsOpen(Exception):
    """apps whose files would change are running: their names"""


def same_file(a, b):
    if a.stat().st_size != b.stat().st_size:
        return False
    with open(a, 'rb') as x, open(b, 'rb') as y:
        while True:
            p, q = x.read(state.CHUNK), y.read(state.CHUNK)
            if p != q:
                return False
            if not p:
                return True


def accepted(rcv):
    """the saved file list, checked once more against the groups that were asked for"""
    asked = [g for g in rcv.st.get('groups') or [] if isinstance(g, str)]
    try:
        return check.manifest(rcv.files(), asked)[0]
    except check.BadPeer:
        return []


def behind_link(rel):
    """is the path, or a folder on the way to it, a symbolic link?"""
    p = items.HOME
    for part in rel.split('/'):
        p = p / part
        if p.is_symlink():
            return True
    return False


def make_folders(rel):
    """the folders a file needs; those that hold keys for this user only"""
    p, parts = items.HOME, rel.split('/')[:-1]
    for i, part in enumerate(parts):
        p = p / part
        private = items.is_private('/'.join(parts[:i + 1]))
        if not p.is_dir():
            p.mkdir(mode=0o700 if private else 0o777)
        elif private and p.stat().st_mode & 0o077:
            os.chmod(p, 0o700)


def put(stage, f):
    """one file into place: 'moved', 'kept' (left alone), 'same' or 'none' (not for here)"""
    rel = f['path']
    src, dst = stage / rel, items.HOME / rel
    if rel.startswith(('system/', 'generated/')) or not src.is_file() or src.is_symlink():
        return 'none'                       # system and generated files: after.py
    if behind_link(rel) or (dst.exists() and not dst.is_file()):
        return 'kept'
    make_folders(rel)
    if dst.exists():
        if same_file(src, dst):
            src.unlink()
            return 'same'
        os.replace(dst, dst.with_name(dst.name + BACKUP))
    try:
        os.replace(src, dst)                # same disk: instant, even for 40 GB
    except OSError:
        shutil.move(str(src), str(dst))
    os.chmod(dst, items.final_mode(rel, f['mode']))
    return 'moved'


def starters(rcv):
    """received files that would run by themselves at login, as they would land here"""
    try:
        stage = rcv.stage()
    except check.BadPeer:
        return []
    return [f['path'] for f in accepted(rcv) if items.starts_by_itself(f['path'])
            and (stage / f['path']).is_file()]


def starters_note(paths):
    if not paths:
        return []
    return [f'{len(paths)} received file{"s" if len(paths) != 1 else ""} start by themselves '
            f'at login: ' + ', '.join(paths[:8]) + ('…' if len(paths) > 8 else '')]


def apply(rcv, answers=None):
    """move what was received into place: (files moved, files kept).
    answers: {'passwords': {new account: password}, 'groups': [groups you confirmed]}"""
    busy = items.running(rcv.st.get('groups') or [])
    if busy:
        raise AppsOpen(', '.join(busy))
    stage = rcv.stage()
    rcv.save(status='putting in place', error='')
    starting = starters(rcv)
    count, problems = {'moved': 0, 'kept': 0, 'same': 0, 'none': 0}, []
    for f in accepted(rcv):
        try:
            count[put(stage, f)] += 1
        except OSError as e:
            problems.append(f"{f['path']}: {e.strerror or e}")
    notes = after.steps(rcv, stage, answers or {})
    notes += starters_note(starting) + trouble(rcv, problems)
    shutil.rmtree(stage, ignore_errors=True)
    rcv.save(status='applied', moved=count['moved'], kept=count['kept'], notes=notes)
    return count['moved'], count['kept']


def trouble(rcv, problems):
    """notes about files that did not make it"""
    notes = []
    failed = rcv.st.get('failed') or []
    counted = rcv.st.get('failed_count')
    for what, lines, n in (('not received', failed, counted if isinstance(counted, int) else len(failed)),
                           ('not put in place', problems, len(problems))):
        if lines:
            notes.append(f'{n} file{"s" if n != 1 else ""} {what}: '
                         + '; '.join(lines[:5]) + ('…' if n > 5 else ''))
    if rcv.st.get('refused'):
        notes.append(f"{rcv.st['refused']} files refused (not part of what you chose)")
    return notes


def apply_when_free(rcv):
    """put in place by itself; apps whose files would change: wait until they are closed,
    APPS_WAIT at most. After that the app shows "Put in place" again."""
    told = ''
    end = time.time() + state.APPS_WAIT
    while time.time() < end:
        try:
            apply(rcv)
        except AppsOpen as e:
            rcv.save(status='waiting for apps', error=str(e))
            if str(e) != told:
                state.notify('Transfer: almost done', f'Close {e} to finish.')
                told = str(e)
            time.sleep(state.APPS_POLL)
            continue
        except Exception as e:              # the background step never just dies
            rcv.save(status='received', auto=False, error=f'could not put in place: {e}')
            state.notify('Transfer: not put in place', 'Open Transfer and press "Put in place".')
            return False
        notes = rcv.st.get('notes') or []
        state.notify('Transfer: done', 'Everything is in place.' + (' ' + '; '.join(notes) if notes else ''))
        return True
    rcv.save(status='apps open', error=told)
    state.notify('Transfer: still waiting', f'Close {told}, open Transfer and press "Put in place".')
    return False


def conflicts(rcv):
    """received files that would replace a different file here"""
    try:
        stage = rcv.stage()
    except check.BadPeer:
        return []
    out = []
    for f in accepted(rcv):
        src, dst = stage / f['path'], items.source(f['path'])
        try:
            if src.is_file() and dst.is_file() and not behind_link(f['path']) \
                    and not same_file(src, dst):
                out.append(f['path'])
        except OSError:
            continue                        # it moved while we looked
    return out
