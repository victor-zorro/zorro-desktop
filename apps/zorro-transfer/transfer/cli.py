"""zorro-transfer: set up another device like this one, over the network (LAN or NetBird).

  zorro-transfer                 the app (Settings → Transfer opens the same)
  zorro-transfer send            offer this device: shows a code (the app runs this)
  zorro-transfer find            senders on the network and among the NetBird peers
  zorro-transfer get HOST [--code CODE] [--groups a,b]
                                 pair with HOST; without --groups: list what it offers
  zorro-transfer continue        go on with an interrupted transfer (no code needed)
  zorro-transfer apply           put what was received into place (.before-transfer backups)
  zorro-transfer status          both sides' progress, as JSON"""
import json
import sys

from . import engine


def main():
    a = sys.argv[1:]
    if not a:
        from .gui import main as gui
        return gui()
    if a[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    if a[0] == 'send':
        pid = int(a[a.index('--gui-pid') + 1]) if '--gui-pid' in a else None
        engine.Sender(gui_pid=pid).run()
        return 0
    if a[0] == 'find':
        for f in engine.discover():
            print(f"{f['name']:24} {f['host']:40} {f['via']}")
        return 0
    if a[0] == 'get' and len(a) >= 2:
        code = a[a.index('--code') + 1] if '--code' in a else input('Code: ').strip()
        r = engine.Receiver()
        try:
            offer = r.offer(a[1], code)
        except PermissionError as e:
            print(f'!! {e}', file=sys.stderr)
            return 1
        if '--groups' not in a:
            for g in offer:
                print(f"{g['id']:12} {g['title']}: {g['files']} files, {g['bytes'] / 1e9:.2f} GB")
            print('then:  zorro-transfer continue --groups ID,ID')
            return 0
        return 0 if r.fetch(a[a.index('--groups') + 1].split(',')) else 1
    if a[0] == 'continue':
        r = engine.Receiver()
        groups = a[a.index('--groups') + 1].split(',') if '--groups' in a else None
        return 0 if r.fetch(groups) else 1
    if a[0] == 'apply':
        moved, kept = engine.Receiver().apply()
        print(f'{moved} files put in place, {kept} left (set up by this device)')
        return 0
    if a[0] == 'status':
        print(json.dumps({'sender': engine.read_state('sender.json'),
                          'receiver': engine.read_state('receiver.json')}, indent=1))
        return 0
    print(__doc__, file=sys.stderr)
    return 2
