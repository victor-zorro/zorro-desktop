"""Run by tools/check-pages inside the test screen: builds every Settings page and prints
one JSON line with what it measured."""
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'apps' / 'zorro-thinkpad'))
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk

CONTROLS = (Gtk.Switch, Gtk.Scale, Gtk.ComboBox, Gtk.Button, Gtk.Entry, Gtk.SpinButton)


def controls(widget):
    """switches, sliders, choices, buttons and fields on a page (rows of a list count once)"""
    if isinstance(widget, Gtk.ListBox):
        return 1
    n = int(isinstance(widget, CONTROLS))
    if isinstance(widget, Gtk.Container) and not isinstance(widget, (Gtk.ComboBox, Gtk.Button)):
        n += sum(controls(c) for c in widget.get_children())
    return n


def measure(win, app_name):
    pages = []
    for menu in list(win.tab_builders) + list(win.groups):
        try:
            group = win.tab(menu)
        except Exception:
            pages.append({'app': app_name, 'menu': menu, 'id': '-', 'title': '-',
                          'error': traceback.format_exc().strip().splitlines()[-1]})
            continue
        for pid, row in group.ids.items():
            page = group.content.get_child_by_name(pid)
            inner = page.get_child()
            inner = inner.get_child() if isinstance(inner, Gtk.Viewport) else inner
            pages.append({'app': app_name, 'menu': menu, 'id': pid,
                          'title': row.get_child().get_text(),
                          'height': inner.get_preferred_height()[1], 'controls': controls(inner)})
    return pages


def main():
    from zsettings import app as zapp
    out = {'pages': []}
    application = Gtk.Application(application_id='org.zorro.pagecheck')

    def activate(a):
        for name in getattr(zapp, 'APPS', {'settings': None}):
            try:
                win = zapp.Win(a, app=name) if hasattr(zapp, 'APPS') else zapp.Win(a)
                out['pages'] += measure(win, name)
                win.destroy()
            except Exception:
                out['pages'].append({'app': name, 'menu': '-', 'id': '-', 'title': '-',
                                     'error': traceback.format_exc().strip().splitlines()[-1]})
        GLib.idle_add(a.quit)
    application.connect('activate', activate)
    application.run([])
    print(json.dumps(out))


if __name__ == '__main__':
    main()
