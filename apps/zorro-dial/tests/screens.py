"""Drive the real Dialer window through its parts, save a screenshot of each, and try the
things a mouse and a keyboard do. Run by screens.sh only: in a private test screen, with a
made-up HOME and fake services."""
import math
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

import helper  # noqa: F401 - puts the Dialer's package on the path

if os.environ.get('ZORRO_DIAL_SCREENS') != '1' or 'tmp' not in str(Path.home()):
    sys.exit('screens.py is run by screens.sh (a private screen and a made-up HOME)')

from dial import cli, state  # noqa: E402
from dial.look import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402
from dial.parts import MODES  # noqa: E402

OUT = Path(sys.argv[1])
DEADLINE = time.time() + 150
NOW = {}                                # 'dial': the window being driven


def dial():
    return NOW['dial']


def shot(name):
    root = Gdk.get_default_root_window()
    Gdk.pixbuf_get_from_window(root, 0, 0, root.get_width(), root.get_height()).savev(
        str(OUT / f'{name}.png'), 'png', [], [])
    print('shot', name, flush=True)


def check(what, ok):
    print('ok  ' if ok else 'FAIL', what, flush=True)


def key(name):
    dial().on_key(None, SimpleNamespace(keyval=Gdk.keyval_from_name(name), state=0))


def type_text(text):
    for ch in text:
        dial().on_key(None, SimpleNamespace(keyval=Gdk.unicode_to_keyval(ord(ch)), state=0))


def mouse(x, y, button=1):
    return SimpleNamespace(x=x, y=y, button=button, state=0)


def click(x, y, button=1):
    dial().on_click(None, mouse(x, y, button))
    dial().on_release(None, mouse(x, y, button))


def part_at(part):
    cx, cy, hub, *_ = dial().fan()
    a = math.radians(-120 + [m[0] for m in MODES].index(part) * 60 + 30)
    return cx + math.cos(a) * hub * 0.8, cy + math.sin(a) * hub * 0.8


def slot(start):
    """where the tile or app whose name starts like this was drawn"""
    found = next((s for s in dial().slots if s[3]['name'].startswith(start)), None)
    if found is None:
        raise LookupError(f'{start!r} is not on the dial: {[s[3]["name"] for s in dial().slots]}')
    return found[0], found[1]


def hover(start):
    dial().on_motion(None, mouse(*slot(start)))


def names():
    return [s[3]['name'] for s in dial().slots]


def conf():
    from dial import config
    return config.load_conf()


def picture():
    GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 3000, 2000).savev(
        str(Path.home() / 'Documents' / 'photo.png'), 'png', [], [])


def shots():
    """(what to do, then seconds to wait before the next step)"""
    yield lambda: NOW.update(dial=cli.Dial()), 3.0
    yield lambda: shot('1-hub'), 0.1
    yield lambda: click(*part_at('music')), 3.0
    yield lambda: shot('2-music-picker'), 0.1
    yield lambda: click(*slot('Headphon')), 0.8
    yield lambda: shot('3-music-connecting'), 4.0
    yield lambda: shot('4-music-connected'), 0.1
    yield lambda: click(*part_at('ai')), 1.0
    yield lambda: type_text('What is a dial?'), 0.4
    yield lambda: shot('5-ai-typing'), 0.1
    yield lambda: key('Return'), 2.2
    yield lambda: shot('6-ai-streaming'), 2.5
    yield lambda: shot('7-ai-answered'), 0.1
    yield lambda: click(*part_at('messages')), 1.5
    yield lambda: shot('8-messages'), 0.1
    yield lambda: hover('Mira'), 1.0
    yield lambda: shot('9-messages-open'), 0.1


def tour_apps():
    yield lambda: click(*part_at('messages')), 0.3     # the kept part again: back to the apps
    yield lambda: check('back on the apps', dial().mode == 'apps'), 0.3
    yield lambda: hover('Editor'), 0.2
    yield lambda: type_text('term'), 0.3
    yield lambda: check('typing searches the apps', names() == ['Terminal']), 0.1
    yield lambda: key('Escape'), 0.3
    yield lambda: dial().on_click(None, mouse(*slot('Editor'))), 1.0       # held still: its menu
    yield lambda: (check('holding an app opens its menu', bool(dial().menu)), shot('10-hold-menu')), 0.1
    yield lambda: key('Escape'), 0.3
    yield lambda: dial().on_click(None, mouse(*slot('Editor'))), 0.1       # drag it to Media
    yield lambda: dial().on_motion(None, mouse(*slot('Player'))), 0.3
    yield lambda: dial().on_release(None, mouse(*slot('Player'))), 0.3
    yield lambda: check('a dragged app moves to that slice', conf()['assign'].get('editor.desktop') == 'Media'), 0.1
    yield lambda: click(*slot('Settings')), 0.3
    yield lambda: check('the gear shows the settings apps', dial().expanded == 'gear'), 0.1
    yield lambda: key('Escape'), 0.3
    yield lambda: click(*dial().labels[0][:2], button=3), 0.2
    yield lambda: (key('BackSpace'), type_text('s'), key('Return')), 0.3
    yield lambda: check('a slice is renamed', conf()['slices'][0]['name'] == 'Wors'), 0.1


def tour_parts():
    yield lambda: click(*part_at('notes')), 1.0
    yield lambda: hover('Work'), 0.9
    yield lambda: check('a notebook unfolds into its notes', 'Plan' in names()), 0.1
    yield lambda: type_text('shopping'), 0.5
    yield lambda: check('typing searches the notes', names() == ['Shopping']), 0.1
    yield lambda: key('Escape'), 0.2
    yield lambda: (picture(), click(*part_at('files'))), 1.0
    yield lambda: hover('Documents'), 0.9
    yield lambda: hover('photo'), 1.5
    yield lambda: (check('a picture is scaled before it is drawn',
                         all(d['picture'].get_width() < 600 for d in dial().previews.values())),
                   shot('11-files-preview')), 0.1
    yield lambda: click(*part_at('messages')), 1.0
    yield lambda: click(*slot('Mira'), button=3), 1.5
    yield lambda: check('right-click dismisses a message', 'Mira' not in names() and len(names()) == 4), 0.1
    yield lambda: click(*slot('Do not')), 1.5
    yield lambda: check('do not disturb is on', dial().parts['messages'].dnd), 0.1
    yield lambda: click(*dial().fan()[:2]), 1.5
    yield lambda: check('the centre clears all', names() == ['Do not disturb', 'Nothing new']), 0.1


def tour_ai():
    yield lambda: click(*part_at('ai')), 0.8
    yield lambda: (type_text('And a ring?'), key('Return')), 1.5
    yield lambda: check('an answer is under way', dial().chat.busy and bool(dial().chat.answer)), 0.1
    yield lambda: key('Escape'), 0.5
    yield lambda: check('Esc stops it, the question is back', dial().chat.text == 'And a ring?'), 0.1
    yield lambda: key('Return'), 0.8
    yield lambda: click(*part_at('music')), 0.3
    yield lambda: check('leaving the part stops the answer', not dial().chat.busy), 0.1
    yield lambda: click(*part_at('ai')), 0.3
    yield lambda: click(*[(a + b) / 2 for a, b in zip(dial().chat_new_at[:2], dial().chat_new_at[2:])]), 0.5
    yield lambda: (check('New chat empties it', dial().chat.blocks() == []), shot('12-ai-new-chat')), 0.1
    yield lambda: (type_text('Again?'), key('Return')), 0.6
    yield lambda: dial().close_dial(), 0.5
    yield lambda: check('closing the dial stops the answer', not dial().chat.busy and dial().closed), 0.1
    yield lambda: cli.toggle(), 1.0                      # as the daemon does on a Super press
    yield lambda: check('a second dial opens', len(state.OPEN) == 1 and not state.OPEN[0].closed), 0.1
    yield lambda: cli.toggle(), 0.3
    yield lambda: check('and closes', state.OPEN == []), 0.1


def broken_dial():
    raise RuntimeError('a dial that cannot be built (made up for this check)')


def tour_daemon():
    """the real program: the daemon and a Super press (zorro-dial again), with a broken config"""
    app = str(helper.APP / 'zorro-dial')
    pid_file = Path(os.environ['XDG_RUNTIME_DIR']) / 'zorro-dial-daemon.pid'
    conf_file = Path.home() / '.config/zorro-dial/config.json'
    real, cli.Dial = cli.Dial, broken_dial
    yield lambda: check('a dial that fails keeps the Super key alive', cli.toggle() is True and state.OPEN == []), 0.1
    yield lambda: setattr(cli, 'Dial', real), 0.1
    yield lambda: conf_file.write_text('[]'), 0.1
    yield lambda: NOW.update(daemon=subprocess.Popen([sys.executable, app, '--daemon'])), 2.5
    yield lambda: check('the daemon wrote its pid', pid_file.read_text() == str(NOW['daemon'].pid)), 0.1
    yield lambda: subprocess.run([sys.executable, app], timeout=10), 1.5
    yield lambda: shot('14-daemon-broken-config'), 0.1
    yield lambda: subprocess.run([sys.executable, app], timeout=10), 0.8
    yield lambda: conf_file.write_text('{"slices": []}'), 0.1
    yield lambda: subprocess.run([sys.executable, app], timeout=10), 1.5
    yield lambda: subprocess.run([sys.executable, app], timeout=10), 0.8
    yield lambda: check('the daemon lives through four Super presses', NOW['daemon'].poll() is None), 0.1
    yield lambda: NOW['daemon'].terminate(), 0.8
    yield lambda: check('and ends when asked', NOW['daemon'].poll() is not None and not pid_file.exists()), 0.1


def no_service():
    yield lambda: NOW.update(dial=cli.Dial()), 1.5
    yield lambda: click(*part_at('ai')), 1.5
    yield lambda: (type_text('Anyone there?'), key('Return')), 1.0
    yield lambda: shot('13-ai-no-service'), 0.1
    yield lambda: check('one calm line', dial().chat.problem == 'The AI service is not running.'), 0.1


def run(steps):
    def advance():
        step = next(steps, None)
        if step is None or time.time() > DEADLINE:
            Gtk.main_quit()
            return False
        try:
            step[0]()
        except Exception:               # noqa: BLE001 - show it and stop, never hang
            traceback.print_exc()
            Gtk.main_quit()
            return False
        GLib.timeout_add(int(step[1] * 1000), advance)
        return False
    GLib.timeout_add(200, advance)
    Gtk.main()


def everything():
    for steps in (shots, tour_apps, tour_parts, tour_ai, tour_daemon):
        yield from steps()


if __name__ == '__main__':
    state.RESIDENT = True               # closing the dial must not end this loop
    run(no_service() if os.environ.get('NO_AI') else everything())
