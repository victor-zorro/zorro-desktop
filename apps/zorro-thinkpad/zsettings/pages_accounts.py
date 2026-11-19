"""app: Accounts: SoundCloud (zorro-music) and Obsidian (notes, Obsidian Sync)"""
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

from .base import APPS, HOME, run, spawn, write_atomic
from .ui import Pages, heading, idle, later, note
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gdk, Gtk  # noqa: E402

MUSIC_CONF = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config')) / 'zorro-music' / 'config.json'
GOOGLE_PROFILE = HOME / '.local/share/firefox-google'
YTDLP = shutil.which('yt-dlp', path=f'{HOME}/.local/bin:{os.environ.get("PATH", "")}')


def music_conf():
    try:
        return json.loads(MUSIC_CONF.read_text())
    except (OSError, ValueError):
        return {}


def save_music_conf(**kv):
    c = music_conf()
    c.update(kv)
    write_atomic(MUSIC_CONF, json.dumps(c, indent=2) + '\n')


def soundcloud_state():
    """'ok' (signed in and accepted), 'expired' (a login cookie SoundCloud no longer accepts),
    'none' (not signed in), 'no-ytdlp'. Only asks yt-dlp; never reads the token itself.
    A profile page (SoundCloud's own) makes yt-dlp verify the login; a search does not."""
    if not YTDLP:
        return 'no-ytdlp'
    try:
        r = subprocess.run([YTDLP, '--cookies-from-browser', f'firefox:{GOOGLE_PROFILE}', '--flat-playlist',
                            '--playlist-end', '1', '--simulate', 'https://soundcloud.com/soundcloud'],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return 'none'
    err = r.stderr.lower()
    if 'token is invalid' in err:
        return 'expired'
    if 'verifying login token' in (r.stdout + r.stderr).lower():
        return 'ok'                     # a profile page checks the login; no complaint: valid
    # no complaint: signed in when the login cookie is there
    music = APPS / 'zorro-music' / 'zorro-music'
    try:
        import importlib.machinery
        import importlib.util
        spec = importlib.util.spec_from_loader('zm', importlib.machinery.SourceFileLoader('zm', str(music)))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return 'ok' if m.firefox_profile() else 'none'
    except (OSError, SyntaxError, ImportError):
        return 'none'


def open_in_google_window(url):
    """a page in the Google-apps Firefox window (that profile is where the player looks)"""
    running = 'GoogleApps' in run('wmctrl', '-lx')
    if running:
        spawn(['firefox', '--profile', str(GOOGLE_PROFILE), '--new-tab', url])
    else:
        spawn(['firefox', '--new-instance', '--class', 'GoogleApps', '--profile', str(GOOGLE_PROFILE), url])


DIAL_CONF = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config')) / 'zorro-dial' / 'config.json'


def dial_conf():
    try:
        return json.loads(DIAL_CONF.read_text())
    except (OSError, ValueError):
        return {}


def set_dial_hidden(path, hidden):
    """leave a vault out of the Dialer's Notes part (or bring it back); keeps the rest of its config"""
    c = dial_conf()
    hide = [p for p in c.get('notes_hide_vaults', []) if p != path] + ([path] if hidden else [])
    c['notes_hide_vaults'] = hide
    DIAL_CONF.parent.mkdir(parents=True, exist_ok=True)
    tmp = DIAL_CONF.with_suffix('.tmp')
    tmp.write_text(json.dumps(c, indent=2) + '\n')
    tmp.replace(DIAL_CONF)


def obsidian_vaults():
    try:
        from zorro_util import vaults               # apps/zorro-fx, on the path via ui.py
        return sorted((str(p) for p in vaults()), key=str.lower)
    except ImportError:
        pass
    try:
        vs = json.loads((HOME / '.config/obsidian/obsidian.json').read_text()).get('vaults', {}).values()
    except (OSError, ValueError):
        return []
    return sorted((v['path'] for v in vs if os.path.isdir(v.get('path', ''))), key=str.lower)


def obsidian_state():
    cfg = HOME / '.config/obsidian/obsidian.json'
    try:
        vaults = json.loads(cfg.read_text()).get('vaults', {})
    except (OSError, ValueError):
        vaults = {}
    v = next((x for x in vaults.values() if x.get('open')), None) or next(iter(vaults.values()), None)
    path = Path(v['path']) if v and v.get('path') else None
    sync = False
    if path:
        try:
            cp = json.loads((path / '.obsidian/core-plugins.json').read_text())
            sync = bool(cp.get('sync')) if isinstance(cp, dict) else 'sync' in cp   # new / old format
        except (OSError, ValueError):
            sync = False
    notes = sum(1 for _ in path.rglob('*.md')) if path and path.is_dir() else 0
    return {'installed': bool(shutil.which('obsidian')), 'vault': str(path) if path else '',
            'notes': notes, 'sync': sync}


EVERNOTE_STEPS = [
    ('1. The download tool (once). Open source; it fetches every notebook through your own '
     'Evernote account.', ['pipx install evernote-backup']),
    ('2. Fetch everything into ~/Evernote-export. The first command asks for your Evernote '
     'login; nothing else leaves the laptop. Run them one after the other:',
     ['mkdir -p ~/Evernote-export && cd ~/Evernote-export',
      'evernote-backup init-db', 'evernote-backup sync']),
    ('VAULTS', []),
    ('4. Check: open each vault in Obsidian (bottom left: the vault name → Manage vaults) and look '
     'at a few web clippings, tables and checklists. Encrypted Evernote notes cannot be converted: '
     'decrypt those in Evernote first. Pressing "Make the vaults" again later only brings in what '
     'is new or changed in Evernote; notes you edited in Obsidian are left alone.', []),
    ('5. Sync, per vault: Settings → Sync → create a remote vault (its own name, your own '
     'encryption password) → connect. On the Android phone: the Obsidian app → Sync → the same '
     'vaults. Obsidian Sync Plus takes up to 10 vaults.', []),
    ('6. Keep ~/Evernote-export until everything is checked; then cancel Evernote.', []),
]
VAULTS_TOOL = APPS.parent / 'extras/evernote-to-obsidian/evernote-to-vaults'


def vaults_panel(box):
    """3: every notebook its own vault in ~/Notes: pick which, and their names; then make them"""
    box.add(Gtk.Label(label='3. Make the vaults: every notebook becomes its own Obsidian vault in '
                            '~/Notes (pictures, checklists, tables and tags included). Untick a notebook '
                            'to leave it out; give two notebooks the same vault name to put them '
                            'together (each in its own folder). Close Obsidian first, then it lists '
                            'the new vaults by itself.',
                      xalign=0, wrap=True, max_width_chars=70, margin_top=6))
    grid = Gtk.Grid(column_spacing=10, row_spacing=4, margin_start=14)
    box.add(grid)
    out = Gtk.Label(xalign=0, wrap=True, selectable=True, max_width_chars=70, margin_start=14)
    out.get_style_context().add_class('monospace')
    rows = []
    try:
        books = json.loads(subprocess.run([str(VAULTS_TOOL), '--list'], capture_output=True,
                                          text=True, timeout=20).stdout or '[]')
    except (OSError, ValueError, subprocess.TimeoutExpired):
        books = []
    if not books:
        grid.attach(Gtk.Label(label='Nothing downloaded yet: do step 2 first, then reopen this.',
                              xalign=0), 0, 0, 1, 1)
        return
    grid.attach(Gtk.Label(label='Notebook', xalign=0), 0, 0, 1, 1)
    grid.attach(Gtk.Label(label='Notes', xalign=1), 1, 0, 1, 1)
    grid.attach(Gtk.Label(label='Vault in ~/Notes', xalign=0), 2, 0, 1, 1)
    for i, nb in enumerate(books, 1):
        cb = Gtk.CheckButton(label=nb['name'], active=nb['notes'] > 0)
        grid.attach(cb, 0, i, 1, 1)
        grid.attach(Gtk.Label(label=str(nb['notes']), xalign=1), 1, i, 1, 1)
        e = Gtk.Entry(text=nb['vault'], width_chars=22)
        grid.attach(e, 2, i, 1, 1)
        rows.append((nb['name'], cb, e))
    btn = Gtk.Button(label='Make the vaults', halign=Gtk.Align.START, margin_start=14)
    btn.get_style_context().add_class('suggested-action')
    box.add(btn)
    box.add(out)

    def make(_b):
        if subprocess.run(['pgrep', '-f', 'evernote-backup sync'], capture_output=True).returncode == 0:
            out.set_text('Evernote is still downloading (step 2): wait until it is done.')
            return
        args = [str(VAULTS_TOOL)]
        for name, cb, e in rows:
            if not cb.get_active():
                args += ['--skip', name]
            elif e.get_text().strip():
                args += ['--map', f'{name}={e.get_text().strip()}']
        btn.set_sensitive(False)
        out.set_text('Working…')
        lines = []

        def work():
            p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for ln in p.stdout:
                lines.append(ln.rstrip())
                idle(lambda t='\n'.join(lines[-14:]): out.set_text(t) and False)
            p.wait()
            idle(lambda: btn.set_sensitive(True) or False)
        threading.Thread(target=work, daemon=True).start()
    btn.connect('clicked', make)


def copy_text(text):
    Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)


def evernote_dialog(parent):
    """the steps, with a Copy button per command (Obsidian's live preview makes copying hard)"""
    dlg = Gtk.Dialog(title='Moving from Evernote to Obsidian', transient_for=parent, modal=False)
    dlg.set_default_size(640, 620)
    sw = Gtk.ScrolledWindow(vexpand=True)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=18)
    status = Gtk.Label(xalign=0)
    for text, cmds in EVERNOTE_STEPS:
        if text == 'VAULTS':
            vaults_panel(box)
            continue
        box.add(Gtk.Label(label=text, xalign=0, wrap=True, selectable=True, max_width_chars=70,
                          margin_top=6))
        for cmd in cmds:
            row = Gtk.Box(spacing=8, margin_start=14)
            e = Gtk.Entry(text=cmd, editable=False, hexpand=True)
            e.get_style_context().add_class('monospace')
            row.add(e)
            b = Gtk.Button(label='Copy')
            b.connect('clicked', lambda _b, c=cmd: (copy_text(c), status.set_text(f'Copied: {c}')))
            row.add(b)
            box.add(row)
    sw.add(box)
    dlg.get_content_area().add(sw)
    foot = Gtk.Box(spacing=8, margin=12)
    foot.pack_start(status, True, True, 0)
    b = Gtk.Button(label='Open a terminal')
    b.connect('clicked', lambda _b: spawn(['x-terminal-emulator'] if shutil.which('x-terminal-emulator')
                                           else ['kitty']))
    foot.add(b)
    b = Gtk.Button(label='Close')
    b.connect('clicked', lambda _b: dlg.destroy())
    foot.add(b)
    dlg.get_content_area().add(foot)
    dlg.show_all()


class AccountsPages:
    """Accounts (a setup tab): SoundCloud and Obsidian - a mixin of the app window"""

    def accounts_pages(self):
        sc, ob = Pages(), Pages()
        self.acc_msg = [note(), note()]
        sc.footer(self.acc_msg[0])
        ob.footer(self.acc_msg[1])

        sc.add(heading('SoundCloud', 'SoundCloud'))
        self.sc_state = Gtk.Label(xalign=0, wrap=True)
        sc.add(self.sc_state)
        row = Gtk.Box(spacing=8, margin_top=6)
        b = Gtk.Button(label='Log in to SoundCloud')
        b.get_style_context().add_class('suggested-action')
        b.connect('clicked', lambda _b: (open_in_google_window('https://soundcloud.com/signin'),
                                         self.acc_say(0, 'Sign in there, then click Check again')))
        row.add(b)
        b = Gtk.Button(label='Check again')
        b.connect('clicked', lambda _b: self.sc_check())
        row.add(b)
        sc.add(row)
        grid = Gtk.Grid(column_spacing=12, row_spacing=8, margin_top=10)
        grid.attach(Gtk.Label(label='Your SoundCloud name', xalign=0), 0, 0, 1, 1)
        user = Gtk.Entry(placeholder_text='the part after soundcloud.com/', width_chars=26,
                         text=music_conf().get('user', ''))
        user.connect('changed', lambda e: later('sc-user', lambda: save_music_conf(
            user=e.get_text().strip().strip('/'))))
        grid.attach(user, 1, 0, 1, 1)
        sc.add(grid)
        sc.add(note('The music player borrows your SoundCloud login from the Google-apps window '
                    '(its own Firefox profile): sign in there once and your likes and playlists '
                    'play, in Go+ quality when you have it. No password is stored here. Without '
                    'login: public free tracks. Your name is needed for "My likes" in the Dialer.'))

        ob.add(heading('Obsidian', 'Obsidian'))
        self.ob_state = Gtk.Label(xalign=0, wrap=True)
        ob.add(self.ob_state)
        row = Gtk.Box(spacing=8, margin_top=6)
        b = Gtk.Button(label='Open Obsidian')
        b.get_style_context().add_class('suggested-action')
        b.connect('clicked', lambda _b: spawn(['obsidian']))
        row.add(b)
        b = Gtk.Button(label='Moving from Evernote: the steps')
        b.connect('clicked', lambda _b: evernote_dialog(self))
        row.add(b)
        b = Gtk.Button(label='Check again')
        b.connect('clicked', lambda _b: self.ob_check())
        row.add(b)
        ob.add(row)
        ob.add(heading('Vaults in the Dialer', 'Vaults'))
        self.ob_vaults = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        ob.add(self.ob_vaults)
        ob.add(note('The Dialer\'s Notes part shows the ticked vaults: each unfolds into its folders '
                    'and notes; Recent, Tags and search cover them all. New vaults are ticked.'))
        ob.add(note('Log in inside Obsidian: Settings (gear, bottom left) → General → Account → '
                    'Log in, with your Obsidian account (obsidian.md). Then Settings → Core '
                    'plugins → Sync on → Sync → choose or create the remote vault, with your own '
                    'encryption password. On the Android phone: the same account and vault.'))
        self.when_shown('accounts', self.sc_check)       # yt-dlp asks soundcloud.com
        idle(self.ob_check)
        return sc, ob

    def acc_say(self, i, text):
        self.acc_msg[i].set_text(text)

    def sc_check(self):
        self.sc_state.set_text('Checking the SoundCloud login…')

        def work():
            st = soundcloud_state()
            idle(lambda: self.sc_state.set_text({
                'ok': '✓ Signed in: your likes and playlists can play',
                'expired': '⚠ The SoundCloud login has expired: log in again (button below)',
                'none': '○ Not signed in: public free tracks only (log in below)',
                'no-ytdlp': '⚠ yt-dlp is missing: run apps/zorro-music/install.sh'}[st]) and False)
        threading.Thread(target=work, daemon=True).start()
        return False

    def ob_check(self):
        s = obsidian_state()
        if not s['installed']:
            text = '⚠ Obsidian is not installed: run ./update-extras.sh'
        elif not s['vault']:
            text = '○ Installed; no vault yet. Open Obsidian and create one (e.g. ~/Notes)'
        else:
            text = (f'✓ Vault {s["vault"].replace(str(HOME), "~")} · {s["notes"]} notes · '
                    + ('Sync on' if s['sync'] else 'Sync not switched on yet'))
        self.ob_state.set_text(text)
        self.ob_fill_vaults()
        return False

    def ob_fill_vaults(self):
        for c in self.ob_vaults.get_children():
            c.destroy()
        hide = set(dial_conf().get('notes_hide_vaults', []))
        vs = obsidian_vaults()
        if not vs:
            self.ob_vaults.add(Gtk.Label(label='No vaults yet', xalign=0))
        for path in vs:
            cb = Gtk.CheckButton(label=path.replace(str(HOME), '~'), active=path not in hide)
            cb.connect('toggled', lambda b, p=path: set_dial_hidden(p, not b.get_active()))
            self.ob_vaults.add(cb)
        self.ob_vaults.show_all()
