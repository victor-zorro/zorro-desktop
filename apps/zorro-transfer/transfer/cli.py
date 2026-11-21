"""zorro-transfer: set up another device like this one, over the network (LAN or NetBird).

  zorro-transfer [--send|--get]  the app (Settings → Desktop → Transfer opens the same),
                                 on the sending or the getting side
  zorro-transfer send            offer this device: shows a code (the app runs this)
  zorro-transfer find            senders on the network and among the NetBird peers
  zorro-transfer get HOST [--code CODE] [--groups a,b]
                                 pair with HOST; without --groups: list what it offers
  zorro-transfer continue        go on with an interrupted transfer (no code needed)
  zorro-transfer apply           put what was received into place (.before-transfer backups)
  zorro-transfer status          both sides' progress, as JSON"""
import getpass
import json
import sys

from . import check, find, net, place, state
from .receiver import Receiver
from .sender import Sender


def option(a, name):
    """the value after --name, None when it is not given"""
    return a[a.index(name) + 1] if name in a and a.index(name) + 1 < len(a) else None


def send(a):
    pid = option(a, '--gui-pid')
    Sender(gui_pid=int(pid) if pid else None).run()
    return 0


def found(_a):
    for f in find.discover():
        print(f"{f['name']:24} {f['host']:40} {f['via']}")
    return 0


def get(a):
    if len(a) < 2:
        return usage()
    code = option(a, '--code') or input('Code: ').strip()
    r = Receiver()
    offer = r.offer(a[1], code.replace(' ', ''))
    groups = option(a, '--groups')
    if groups:
        return 0 if r.fetch(groups.split(',')) else 1
    for g in offer:
        print(f"{g['id']:12} {g['title']}: {g['files']} files, {g['bytes'] / 1e9:.2f} GB")
    print('then:  zorro-transfer continue --groups ID,ID')
    return 0


def go_on(a):
    groups = option(a, '--groups')
    return 0 if Receiver().fetch(groups.split(',') if groups else None) else 1


def ask_password(acc):
    groups = ', '.join(acc['groups']) or 'none'
    print(f"New account {acc['name']} ({acc['full'] or 'no name'}); groups: {groups}")
    for _ in range(5):
        pw = getpass.getpass('  password, empty to skip: ')
        if not pw or pw == getpass.getpass('  again: '):
            return pw
        print('  not the same, once more')
    return ''


def apply(_a):
    r = Receiver()
    passwords = {acc['name']: ask_password(acc) for acc in r.new_accounts()}
    try:
        moved, kept = r.apply(passwords)
    except place.AppsOpen as e:
        print(f'!! close these first: {e}', file=sys.stderr)
        return 1
    print(f'{moved} files put in place, {kept} left (set up by this device)')
    for note in state.read_state('receiver.json').get('notes') or []:
        print(note)
    return 0


def status(_a):
    print(json.dumps({'sender': state.read_state('sender.json'),
                      'receiver': state.read_state('receiver.json')}, indent=1))
    return 0


def usage(_a=None):
    print(__doc__, file=sys.stderr)
    return 2


COMMANDS = {'send': send, 'find': found, 'get': get, 'continue': go_on, 'apply': apply,
            'status': status}


def main():
    a = sys.argv[1:]
    if not a or a[0] in ('--send', '--get'):
        from .pages.window import main as gui
        return gui(a[0] if a else None)
    if a[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    try:
        return COMMANDS.get(a[0], usage)(a)
    except (net.TooOld, state.Busy, check.BadPeer, OSError, ValueError) as e:
        print(f'!! {e}', file=sys.stderr)
        return 1
