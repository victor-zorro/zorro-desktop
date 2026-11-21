"""The dialog that shows the groups your own account joins on this device, before the admin
password is asked. Plain ones are ticked; powerful ones (admin, every key you type…) are not,
unless you tick them."""
from .. import generated
from .widgets import Gtk

ABOUT = ('On the other device your account was in these groups. Your account here joins the '
         'ticked ones (from the next login).')


def build(win, groups):
    d = Gtk.Dialog(title='Your groups', transient_for=win, modal=True)
    d.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Go on', Gtk.ResponseType.OK)
    box = d.get_content_area()
    box.set_border_width(16)
    box.set_spacing(8)
    box.add(Gtk.Label(label=ABOUT, xalign=0, wrap=True, max_width_chars=50))
    ticks = {}
    for g, powerful in groups:
        text = f'{g}: {generated.POWERFUL[g]}' if powerful else g
        ticks[g] = Gtk.CheckButton(label=text, active=not powerful)
        box.add(ticks[g])
    d.set_default_response(Gtk.ResponseType.OK)
    d.show_all()
    return d, ticks


def ask_groups(win, groups):
    """the groups you ticked, [] when there are none to ask about, None for Cancel"""
    if not groups:
        return []
    d, ticks = build(win, groups)
    try:
        if d.run() != Gtk.ResponseType.OK:
            return None
        return [g for g, cb in ticks.items() if cb.get_active()]
    finally:
        d.destroy()
