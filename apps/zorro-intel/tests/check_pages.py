#!/usr/bin/python3
"""Build every page of Intelligence once, in a private test screen, and measure it (RULES.md):
a page must open, fit the window's page area without scrolling, and hold at most 8 controls.

  python3 apps/zorro-intel/tests/check_pages.py      exit 1 when a page fails

Needs Xvfb (apt install xvfb, or XVFB=/path/to/Xvfb). Nothing shows on your screen; the app
runs with an empty test home and no services, so none of your files are read or changed.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
DISPLAY = os.environ.get('INTEL_TEST_DISPLAY', ':96')
MAX_CONTROLS, MAX_MENU = 8, 7


def controls(widget, Gtk):
    """switches, choices, buttons and fields on a page (a list counts once, whatever is in it)"""
    if isinstance(widget, Gtk.ListBox) or type(widget).__name__ == 'Conversation':
        return 1
    kinds = (Gtk.Switch, Gtk.Scale, Gtk.ComboBox, Gtk.Button, Gtk.Entry)
    n = int(isinstance(widget, kinds) and widget.get_visible())
    if isinstance(widget, Gtk.Container) and not isinstance(widget, kinds):
        n += sum(controls(c, Gtk) for c in widget.get_children())
    return n


def measure():
    """inside the test screen: one line of JSON with what every page measures"""
    sys.path.insert(0, str(APP))
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk
    from intel import app as intel_app
    from intel.cli import PAGES
    win = intel_app.Window(None)
    width, height = intel_app.SIZE[0] - intel_app.MENU_WIDTH, intel_app.SIZE[1]
    out = {'area': [width, height], 'menu': len(win.menu.get_children()), 'pages': []}
    for name in PAGES:
        try:
            page = win.page(name)
            for bar in (w for w in page.get_children() if type(w).__name__.endswith('Bar')):
                bar.show()              # measured at its fullest: every "not running" line showing
            out['pages'].append({'name': name, 'height': page.get_preferred_height_for_width(width)[1],
                                 'width': page.get_preferred_width()[0], 'controls': controls(page, Gtk)})
        except Exception:               # noqa: BLE001 - the report names the page that broke
            out['pages'].append({'name': name, 'error': traceback.format_exc().strip().splitlines()[-1]})
    win.destroy()
    print(json.dumps(out))


def run_inside(home):
    env = {k: v for k, v in os.environ.items() if k not in ('DISPLAY', 'WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS')}
    run = Path(home) / 'run'
    run.mkdir(mode=0o700)
    env.update(HOME=home, XDG_RUNTIME_DIR=str(run), DISPLAY=DISPLAY, GDK_BACKEND='x11',
               XDG_CONFIG_HOME=f'{home}/.config', XDG_DATA_HOME=f'{home}/.local/share',
               XDG_STATE_HOME=f'{home}/.local/state', XDG_CACHE_HOME=f'{home}/.cache')
    xvfb = os.environ.get('XVFB') or shutil.which('Xvfb')
    screen = subprocess.Popen([xvfb, DISPLAY, '-screen', '0', '1280x800x24', '-nolisten', 'tcp'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1)
        done = subprocess.run(['dbus-run-session', sys.executable, __file__, '--inside'], env=env,
                              capture_output=True, text=True, timeout=120)
    finally:
        screen.terminate()
        screen.wait(5)
    lines = [x for x in done.stdout.splitlines() if x.startswith('{')]
    return (json.loads(lines[-1]) if lines else None), done.stderr[-2000:]


def problems(result):
    width, height = result['area']
    bad = [f'the menu has {result["menu"]} entries'] if result['menu'] > MAX_MENU else []
    for p in result['pages']:
        marks = []
        if p.get('error'):
            marks.append('DOES NOT OPEN: ' + p['error'])
        else:
            if p['height'] > height:
                marks.append(f'too tall ({p["height"]} px of {height})')
            if p['width'] > width:
                marks.append(f'too wide ({p["width"]} px of {width})')
            if p['controls'] > MAX_CONTROLS:
                marks.append(f'{p["controls"]} controls')
        size = '' if p.get('error') else f'{p["width"]:4}x{p["height"]:<4} {p["controls"]} controls'
        print(f'{p["name"]:8} {size:24} {"; ".join(marks) or "ok"}')
        bad += [f'{p["name"]}: {m}' for m in marks]
    return bad


def main():
    if '--inside' in sys.argv:
        measure()
        return 0
    if not (os.environ.get('XVFB') or shutil.which('Xvfb')):
        print('Xvfb not found: apt install xvfb, or set XVFB=/path/to/Xvfb')
        return 2
    with tempfile.TemporaryDirectory(prefix='zin-pages-', dir='/tmp') as home:
        result, err = run_inside(home)
    if result is None:
        print('the app did not start:\n' + err)
        return 1
    bad = problems(result)
    print(f'{len(result["pages"])} pages, area {result["area"][0]}x{result["area"][1]}: '
          + (f'{len(bad)} problems' if bad else 'all fit'))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
