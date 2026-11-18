"""settings files, small helpers and the indicator client"""
import json


import os
import socket
import subprocess
from pathlib import Path

HOME = Path.home()
APPS = Path(os.path.realpath(__file__)).parents[2]        # the repo's apps/ folder
CONF = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config')) / 'zorro-thinkpad' / 'config.json'
RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
SOCK = RUNTIME / 'zorro-thinkpad.sock'
STATE = RUNTIME / 'zorro-thinkpad.state'
KBD_LED = Path('/sys/class/leds/tpacpi::kbd_backlight')
EXTRA_BUTTONS = 'ThinkPad Extra Buttons'

# evdev codes from the ThinkPad Extra Buttons device that X cannot deliver (code + 8 > 255)
EVDEV_KEYS = {248: 'mic-mute',              # F4  KEY_MICMUTE
              444: 'settings',              # F9  KEY_NOTIFICATION_CENTER
              445: 'lte-on',                # F10 KEY_PICKUP_PHONE
              446: 'lte-off',               # F11 KEY_HANGUP_PHONE
              0x27a: 'screenshot-region'}   # Fn+PrtSc KEY_SELECTIVE_SCREENSHOT

STAR_ACTIONS = {                            # what the star key (F12) can do
    'screenshot': ('Screenshot', ['zorro-shot']),
    'screenshot-region': ('Screenshot of an area', ['zorro-shot', '--region']),
    'lock': ('Lock the screen', ['zorro-lock']),
    'drive': ('Drive app', ['zorro-drive']),
    'terminal': ('Terminal', ['x-terminal-emulator']),
    'files': ('File manager', ['xdg-open', str(Path.home())]),
    'launcher': ('App launcher (rofi)', ['rofi', '-show', 'drun']),
    'custom': ('Custom command…', None),
}


_conf_cache = {'key': None, 'text': '{}'}


def load_conf():
    """the settings (a fresh dict each call); the file is only re-read when it changed"""
    try:
        st = CONF.stat()
        key = (st.st_mtime_ns, st.st_size)
        if key != _conf_cache['key']:
            _conf_cache.update(key=key, text=CONF.read_text())
        data = json.loads(_conf_cache['text'])
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_atomic(path, text):
    """write via a unique temp file + rename: readers never see half a file"""
    import tempfile
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.')
    try:
        with os.fdopen(fd, 'w') as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_conf(c):
    write_atomic(CONF, json.dumps(c, indent=2) + '\n')


def run(*cmd, timeout=10):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ''


def spawn(cmd):
    try:
        subprocess.Popen(cmd, start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        osd('dialog-warning-symbolic', None, f'Not installed: {cmd[0]}')


# ---- indicator (OSD) client -------------------------------------------------------------

def osd(icon, value, text=''):
    """Show the indicator; value 0-100 draws a level bar, None shows text only."""
    msg = json.dumps({'icon': icon, 'value': value, 'text': text}).encode()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.sendto(msg, str(SOCK))
    except OSError:                      # keyd not running: fall back to a notification
        body = text or (f'{value}%' if value is not None else '')
        hints = ['-h', 'string:x-dunst-stack-tag:zorro-osd']
        if value is not None:
            hints += ['-h', f'int:value:{value}']
        run('notify-send', '-a', 'ThinkPad', '-t', '1500', *hints, '-i', icon, body or ' ')




def update_conf(section, **kv):
    """change some settings; locked, because keyd and the app both write the file"""
    import fcntl
    CONF.parent.mkdir(parents=True, exist_ok=True)
    with open(CONF.parent / '.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        c = load_conf()
        if section:
            if not isinstance(c.get(section), dict):
                c[section] = {}
            c[section].update(kv)
        else:
            c.update(kv)
        save_conf(c)
    return c


def sysread(p, default=''):
    try:
        return Path(p).read_text().strip()
    except OSError:
        return default
