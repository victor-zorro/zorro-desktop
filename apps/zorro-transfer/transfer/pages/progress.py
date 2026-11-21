"""The getting page, last step: the progress of the copy, then "Put in place".
The copy is a process of its own (zorro-transfer continue); this page shows receiver.json."""
from .. import place, state
from ..receiver import Receiver
from .groups import ask_groups
from .passwords import ask_passwords
from .widgets import Gtk, ROUTE, background, btn, eta, human, label, num, spawn

WORKING = ('starting', 'receiving', 'reconnecting', 'putting in place', 'waiting for apps')


def shown_status(st):
    """the saved status, as it counts now (the process that wrote it may be gone)"""
    status, running = st.get('status', ''), state.is_transfer(st.get('pid'))
    if status in ('starting', 'receiving', 'reconnecting') and not running:
        return 'interrupted'
    if status == 'putting in place' and not running:
        return 'received'
    if status == 'received' and st.get('auto') and running:
        return 'putting in place'
    if status == 'waiting for apps' and not (st.get('auto') and running):
        return 'apps open'
    return status


def text_for(status, st):
    """the line under the bar, for the statuses that need no more than the state"""
    error, total, done, speed = st.get('error', ''), *(num(st.get(k)) for k in ('total', 'done', 'speed'))
    notes = '; '.join(st.get('notes') or [])
    return {
        'receiving': f"{human(speed)}/s · {eta(total - done, speed)}"
                     f"\n{st.get('current', '')}",
        'reconnecting': 'The connection dropped: trying again… (it goes on where it stopped)',
        'interrupted': f'Stopped: {error}. It goes on where it stopped once the other device '
                       f'sends again (open Transfer there: Send this setup).',
        'putting in place': 'Everything is here; putting it in place…',
        'waiting for apps': f'Everything is here. It goes into place by itself once these are '
                            f'closed: {error}',
        'apps open': f'Close these first, then press Put in place again: {error}',
        'applied': f"Done: {st.get('moved', 0)} files put in place"
                   + (f' ({notes})' if notes else '') + '. Log out and in once to see all settings.',
        'failed': f'It did not work: {error}',
    }.get(status)


class Progress:
    def __init__(self, win):
        self.win = win
        win.put(label('Getting the setup', big=True))
        self.head = win.put(label('', dim=True))
        self.bar = win.put(Gtk.ProgressBar(show_text=True))
        self.line = win.put(label('', dim=True))
        self.buttons = win.put(Gtk.Box(spacing=8))
        win.tip()
        self.status = None
        self.replaced = None                # (files replaced, files that start by themselves)
        self.tick()
        win.every(500, self.tick)

    def tick(self):
        st = state.read_state('receiver.json')
        status = shown_status(st)
        total, done = num(st.get('total')), num(st.get('done'))
        self.bar.set_fraction(min(1, done / total) if total else 0)
        self.bar.set_text(f'{human(done)} of {human(total)}' if total else '')
        self.head.set_text(f"From {st.get('sender', '?')}, {ROUTE.get(st.get('route'), '')}")
        if status == 'received':
            self.line.set_text(self.received_text(st))
        elif text_for(status, st) is not None:
            self.line.set_text(text_for(status, st))
        if status != self.status:
            self.status = status
            self.fit_buttons(status)
        return True

    def received_text(self, st):
        if st.get('error'):
            return f"Everything is here, but: {st['error']}"
        if self.replaced is None:
            self.replaced = 'counting'
            background(self, lambda: (len(Receiver().conflicts()), Receiver().starters()),
                       lambda n: setattr(self, 'replaced', n),
                       lambda e: setattr(self, 'replaced', (0, [])))
        if self.replaced == 'counting':
            return 'Everything is here.'
        replaced, starting = self.replaced
        text = 'Everything is here. ' + (
            f'{replaced} of these files replace different ones on this device; those are '
            f'kept as .before-transfer copies.' if replaced
            else 'Nothing on this device gets replaced.')
        return '\n'.join([text] + place.starters_note(starting))

    def fit_buttons(self, status):
        for c in self.buttons.get_children():
            self.buttons.remove(c)
        if status in WORKING:
            self.buttons.add(btn('Go on in the background', self.win.destroy))
        elif status == 'interrupted':
            self.buttons.add(btn('Try again', lambda: spawn('continue'), primary=True))
        elif status in ('received', 'apps open'):
            self.buttons.add(btn('Put in place', self.apply, primary=True))
        elif status in ('applied', 'failed'):
            self.buttons.add(btn('Close', self.win.destroy))
            self.buttons.add(btn('Another transfer', lambda: self.win.go('start')))
        self.buttons.show_all()

    def apply(self):
        r = Receiver()
        people = r.new_accounts()
        passwords = ask_passwords(self.win, people) if people else {}
        mine = ask_groups(self.win, r.groups_to_add()) if passwords is not None else None
        if mine is None:
            return
        self.line.set_text('Putting it in place… (the login look and accounts ask your password)')
        for c in self.buttons.get_children():
            c.set_sensitive(False)

        def work():
            try:
                r.apply(passwords, mine)
            except place.AppsOpen as e:
                r.save(status='apps open', error=str(e))
            except Exception as e:          # the page shows it and offers the button again
                r.save(status='received', auto=False, error=f'could not put in place: {e}')
            finally:
                self.status = None          # the buttons that fit, on the next look
        background(self, work, lambda _: None, lambda _: None, must_finish=True)
