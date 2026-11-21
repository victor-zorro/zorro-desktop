"""Run inside a private test screen by test_window.py: builds the Transfer window's pages
and prints what it saw, as one JSON line. HOME and the state folders are temporary."""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transfer import find, state  # noqa: E402

find.discover = lambda wait=1.5: []         # never the real network
from transfer.pages import groups, window  # noqa: E402

PID = state.STATE / 'window.pid'
seen = {}
win = window.Win('--get')
seen['get page leaves no pid'] = not PID.exists()
win.go('send', False)
seen['send page leaves its pid'] = state.read_pid('window.pid') == os.getpid()
win.go('start')
seen['gone with the page'] = not PID.exists()

win.go('send', False)
state.write_state('sender.json', {'pid': os.getpid(), 'status': 'sending', 'code': '123456',
                                  'sessions': {'0123456789abcdef': {
                                      'status': 'connected', 'updated': time.time(),
                                      'total': float('inf'), 'done': 1, 'speed': float('nan')}}})
seen['endless numbers: the timer goes on'] = win.page.tick() is True
win.page.show_progress = lambda *a: 1 / 0
seen['an error: the timer goes on'] = win.page.tick() is True

d, ticks = groups.build(win, [('sudo', True), ('video', False)])
seen['powerful groups are off'] = (ticks['sudo'].get_active(), ticks['video'].get_active()) == (False, True)
d.destroy()
win.destroy()
seen['gone with the window'] = not PID.exists()
print(json.dumps(seen))
