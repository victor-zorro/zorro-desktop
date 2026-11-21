"""The dialog that asks a password for each new account. Passwords never travel between
the devices: they are typed here. Each account is shown with the groups it would get, so an
account that may run things as admin does not slip in unseen."""
from .widgets import Gtk

ABOUT = ('These people had an account on the other device. Choose a password for each (tell '
         'them; they can change it later). Leave it empty to skip one.')


def describe(a):
    """who it is and what the account may do"""
    groups = ', '.join(a['groups']) or 'none'
    admin = 'ADMIN: may change this device. ' if 'sudo' in a['groups'] else ''
    return f"{a['full'] or a['name']} ({a['name']})\n{admin}Groups: {groups}"


def build(win, people):
    d = Gtk.Dialog(title='New accounts', transient_for=win, modal=True)
    d.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Make the accounts', Gtk.ResponseType.OK)
    box = d.get_content_area()
    box.set_border_width(16)
    box.set_spacing(8)
    about = Gtk.Label(xalign=0, wrap=True, max_width_chars=50)
    about.set_text(ABOUT)
    box.add(about)
    grid = Gtk.Grid(column_spacing=8, row_spacing=6)
    entries = {}
    for i, a in enumerate(people):
        who = Gtk.Label(label=describe(a), xalign=0, wrap=True, max_width_chars=40)
        grid.attach(who, 0, i, 1, 1)
        pair = []
        for j, hint in enumerate(('password', 'again')):
            e = Gtk.Entry(visibility=False, placeholder_text=hint, activates_default=True,
                          valign=Gtk.Align.START)
            grid.attach(e, 1 + j, i, 1, 1)
            pair.append(e)
        entries[a['name']] = pair
    box.add(grid)
    warn = Gtk.Label(xalign=0)
    box.add(warn)
    d.set_default_response(Gtk.ResponseType.OK)
    d.show_all()
    return d, entries, warn


def ask_passwords(win, people):
    """a password for each new account, typed here; {name: password} or None (cancel)"""
    d, entries, warn = build(win, people)
    try:
        while d.run() == Gtk.ResponseType.OK:       # ends with matching passwords or Cancel
            bad = [n for n, p in entries.items() if p[0].get_text() != p[1].get_text()]
            if not bad:
                return {n: p[0].get_text() for n, p in entries.items()}
            warn.set_markup(f'<b>The two passwords differ for {", ".join(bad)}</b>')
        return None
    finally:
        d.destroy()
