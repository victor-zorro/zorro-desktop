"""window theme, picom, kitty and GTK css"""
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from .base import HOME, load_conf, run, spawn, write_atomic


# ---- windows: Openbox theme "Zorro", title bar size, compositor (picom), kitty opacity ---------

WIN_DEFAULTS = {'titlebar': 'medium', 'compositor': True, 'kitty_opacity': 0.88,
                'kitty_blur': True, 'accent': '#19e6ff', 'text': '#d8d8de',
                'font': 'DejaVu Sans', 'font_size': 10, 'term_size': 11, 'text_scale': 1.0}
TITLE_SIZES = {'small': ('Small', 3, 8), 'medium': ('Medium', 6, 10), 'large': ('Large', 9, 12),
               'xl': ('Extra large', 12, 14)}       # name: (label, padding px, button px)
THEME_DIR = HOME / '.local/share/themes/Zorro/openbox-3'
PICOM_CONF = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config')) / 'zorro-settings' / 'picom.conf'
KITTY_CONF = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config')) / 'kitty' / 'zorro.conf'


def win_conf():
    c = dict(WIN_DEFAULTS)
    c.update(load_conf().get('windows', {}))
    return c


def xbm(name, n, pixels):
    """an X bitmap n×n from a set of (x, y) pixels (Openbox button images)"""
    rows = []
    for y in range(n):
        for bx in range(0, n, 8):
            b = 0
            for k in range(8):
                if (bx + k, y) in pixels:
                    b |= 1 << k
            rows.append(f'0x{b:02x}')
    return (f'#define {name}_width {n}\n#define {name}_height {n}\n'
            f'static unsigned char {name}_bits[] = {{ {", ".join(rows)} }};\n')


def button_images(n):
    w = max(1, n // 7)                                   # line thickness
    full = range(n)
    thick = lambda y0: {(x, y) for x in full for y in range(y0, y0 + w)}
    box = lambda x0, y0, s: ({(x, y) for x in range(x0, x0 + s) for y in range(y0, y0 + w)}
                             | {(x, y) for x in range(x0, x0 + s) for y in range(y0 + s - w, y0 + s)}
                             | {(x, y) for y in range(y0, y0 + s) for x in range(x0, x0 + w)}
                             | {(x, y) for y in range(y0, y0 + s) for x in range(x0 + s - w, x0 + s)})
    cross = {(x, y) for x in full for y in full
             if abs(x - y) < w or abs(x + y - (n - 1)) < w}
    s2 = n * 2 // 3
    imgs = {
        'close': cross,
        'max': box(0, 0, n) | thick(0) | thick(w),
        'max_toggled': box(n - s2, 0, s2) | (box(0, n - s2, s2)),
        'iconify': thick(n - w - 1),
        'shade': thick(0) | thick(w),
        'shade_toggled': thick(n - w - 1) | thick(0),
        'desk': {(x, y) for x in full for y in full
                 if (x < n // 2 - 1 or x > n // 2) and (y < n // 2 - 1 or y > n // 2)},
        'desk_toggled': {(x, y) for x in range(n // 3, n - n // 3) for y in range(n // 3, n - n // 3)},
        'bullet': {(x, y) for y in full for x in range(n // 2) if abs(y - n // 2) <= n // 2 - x},
    }
    return {k: xbm(k, n, v) for k, v in imgs.items()}


def colour_or(value, default):
    return value if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) else default


def write_theme(c):
    _, pad, bsize = TITLE_SIZES.get(c['titlebar'], TITLE_SIZES['medium'])
    acc = colour_or(c.get('accent'), WIN_DEFAULTS['accent'])
    fg = colour_or(c.get('text'), WIN_DEFAULTS['text'])
    THEME_DIR.mkdir(parents=True, exist_ok=True)
    for name, data in button_images(bsize).items():
        (THEME_DIR / f'{name}.xbm').write_text(data)
    btn = ''
    for state in ('active', 'inactive'):
        img = '#b8b8c0' if state == 'active' else '#55555c'
        for kind, col in (('unpressed', img), ('hover', acc if state == 'active' else fg),
                          ('pressed', '#ffffff'), ('disabled', '#3a3a40')):
            bg = 'parentrelative' if kind in ('unpressed', 'disabled') else 'flat solid'
            btn += f'window.{state}.button.{kind}.bg: {bg}\n'
            if bg != 'parentrelative':
                btn += f'window.{state}.button.{kind}.bg.color: {"#1c1c22" if kind == "hover" else "#2a2a32"}\n'
            btn += f'window.{state}.button.{kind}.image.color: {col}\n'
        for kind in ('toggled.unpressed', 'toggled.hover', 'toggled.pressed'):
            btn += (f'window.{state}.button.{kind}.bg: parentrelative\n'
                    f'window.{state}.button.{kind}.image.color: {acc}\n')
    text = f"""# Zorro: written by the Zorro app (Desktop → Windows); dark, flat, like the lock screen
border.width: 1
padding.width: 6
padding.height: {pad}
window.handle.width: 0
window.client.padding.width: 0
window.client.padding.height: 0
menu.overlap.x: 0
menu.overlap.y: 0

window.active.border.color: #ff2a4a
window.inactive.border.color: #141417
window.active.title.separator.color: {acc}
window.inactive.title.separator.color: #141417
window.active.client.color: #0b0b0d
window.inactive.client.color: #0b0b0d
window.active.title.bg: flat solid
window.active.title.bg.color: #0e0e12
window.inactive.title.bg: flat solid
window.inactive.title.bg.color: #060607
window.active.label.bg: parentrelative
window.inactive.label.bg: parentrelative
window.active.label.text.color: {fg}
window.inactive.label.text.color: #6f7079
window.label.text.justify: center
window.active.handle.bg: flat solid
window.active.handle.bg.color: #0e0e12
window.inactive.handle.bg: flat solid
window.inactive.handle.bg.color: #060607
window.active.grip.bg: flat solid
window.active.grip.bg.color: #1c1c22
window.inactive.grip.bg: flat solid
window.inactive.grip.bg.color: #0e0e12
{btn}window.active.button.close.hover.image.color: #ff2a4a

menu.border.width: 1
menu.border.color: #2c2c33
menu.separator.color: #2c2c33
menu.title.bg: flat solid
menu.title.bg.color: #0e0e12
menu.title.text.color: {fg}
menu.title.text.justify: center
menu.items.bg: flat solid
menu.items.bg.color: #0b0b0d
menu.items.text.color: {fg}
menu.items.disabled.text.color: #55555c
menu.items.active.bg: flat solid
menu.items.active.bg.color: #1c1c22
menu.items.active.text.color: {acc}

osd.border.width: 1
osd.border.color: #2c2c33
osd.bg: flat solid
osd.bg.color: #0b0b0d
osd.label.bg: parentrelative
osd.label.text.color: {fg}
osd.hilight.bg: flat solid
osd.hilight.bg.color: {acc}
osd.unhilight.bg: flat solid
osd.unhilight.bg.color: #2c2c33
"""
    (THEME_DIR / 'themerc').write_text(text)


def write_picom(c):
    PICOM_CONF.parent.mkdir(parents=True, exist_ok=True)
    PICOM_CONF.write_text(f"""# picom for zorro-desktop: written by the Zorro app (Desktop → Windows)
# only what transparency needs: no shadows, no fades; full-screen windows skip it (battery)
backend = "glx";
vsync = true;
shadow = false;
fading = false;
use-damage = true;
unredir-if-possible = true;
detect-client-opacity = true;
blur-background = {'true' if c['kitty_blur'] else 'false'};
blur-method = "dual_kawase";
blur-strength = 4;
blur-background-exclude = [ "class_g != 'kitty'" ];
""")


def write_kitty(c, composited):
    op = c['kitty_opacity'] if composited else 1.0      # without picom: solid, never broken
    fg = colour_or(c.get('text'), WIN_DEFAULTS['text'])
    acc = colour_or(c.get('accent'), WIN_DEFAULTS['accent'])
    size = min(24, max(6, float(c.get('term_size', 11))))
    write_atomic(KITTY_CONF, '# written by the Zorro app (Desktop → Windows / Text & colours); not in git\n'
                 f'background_opacity {op:.2f}\ndynamic_background_opacity yes\n'
                 f'font_size {size:g}\nforeground {fg}\ncursor {acc}\nselection_background {acc}\n'
                 'selection_foreground #000000\n')


GTK_CSS = [HOME / '.config/gtk-3.0/gtk.css', HOME / '.config/gtk-4.0/gtk.css']


def write_gtk_css(c):
    """font, text colour and accent for GTK apps (new windows pick it up); not in git"""
    font = re.sub(r'[^A-Za-z0-9 ,.-]', '', str(c.get('font', 'DejaVu Sans'))) or 'DejaVu Sans'
    size = min(20, max(6, float(c.get('font_size', 10))))
    fg = colour_or(c.get('text'), WIN_DEFAULTS['text'])
    acc = colour_or(c.get('accent'), WIN_DEFAULTS['accent'])
    css = ('/* written by the Zorro app (Desktop -> Text & colours); not in git */\n'
           f'* {{ font-family: "{font}"; font-size: {size:g}pt; }}\n'
           f'window, label, entry, textview, .view, button, menuitem {{ color: {fg}; }}\n'
           f'selection, *:selected, row:selected {{ background-color: alpha({acc}, 0.35); }}\n'
           f'scale highlight, progressbar progress, switch:checked {{ background-color: {acc}; }}\n')
    for p in GTK_CSS:
        if p.parent.is_dir() and not (p.exists() and 'Zorro app' not in p.read_text()):
            write_atomic(p, css)        # never overwrite a gtk.css someone else wrote


def write_dpi(c):
    """Text size: the screen's font DPI (Xft.dpi, 96 = 100%). GTK, Firefox and the web apps,
    Electron apps (Signal, Obsidian), Openbox and the Zorro apps read it when they start."""
    try:
        scale = min(1.6, max(1.0, float(c.get('text_scale', 1.0))))
    except (TypeError, ValueError):
        scale = 1.0
    dpi = round(96 * scale)
    try:                                # never in the way of the rest of apply_windows
        subprocess.run(['xrdb', '-merge'], input=f'Xft.dpi: {dpi}\n', text=True,
                       capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass


def picom_running():
    return bool(run('pgrep', '-x', 'picom').strip())


def apply_windows(login=False):
    """write theme, picom and kitty settings and make them live"""
    c = win_conf()
    in_vm = subprocess.run(['systemd-detect-virt', '-q']).returncode == 0
    want = bool(c['compositor'] and shutil.which('picom') and not in_vm)
    write_theme(c)
    write_picom(c)
    write_kitty(c, want)
    write_gtk_css(c)
    write_dpi(c)
    if not login:
        run('openbox', '--reconfigure')
    was = picom_running()
    if was:
        run('pkill', '-x', 'picom')
        time.sleep(0.3)
    if want:
        spawn(['picom', '--config', str(PICOM_CONF)])
    for pid in run('pgrep', '-x', 'kitty').split():      # kitty reloads its config
        try:
            os.kill(int(pid), 10)                        # SIGUSR1
        except (OSError, ValueError):
            pass


# ---- zorro-winpos: where windows open, and reopening everything after a restart ----------
WINPOS_CONF = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'zorro-winpos' / 'config.json'


def winpos_conf():
    try:
        return json.loads(WINPOS_CONF.read_text())
    except (OSError, ValueError):
        return {}


_winpos_lock = __import__('threading').Lock()


def set_winpos(key, value):
    with _winpos_lock:                  # two switches flipped quickly: both are kept
        _set_winpos(key, value)


def _set_winpos(key, value):
    """save, switch Firefox's own session restore along, and restart zorro-winpos (it reads its
    settings when it starts; it does not reopen anything when restarted within a login)"""
    c = winpos_conf()
    c[key] = value
    write_atomic(WINPOS_CONF, json.dumps(c, indent=1))
    tool = shutil.which('zorro-winpos')
    if not tool:
        return
    if key == 'restore_session':
        subprocess.run([tool, '--firefox-on' if value else '--firefox-off'], check=False)
    subprocess.run(['pkill', '-x', 'zorro-winpos'], check=False)
    subprocess.Popen([tool], start_new_session=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
