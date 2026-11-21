"""The Dialer's settings: ~/.config/zorro-dial/config.json, checked before use."""
import json
import os
import re
from pathlib import Path

HOME = Path.home()
CONFIG_HOME = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config'))
CONF = CONFIG_HOME / 'zorro-dial' / 'config.json'
ORB_CONF = CONFIG_HOME / 'zorro-orb' / 'config.json'
THINKPAD_CONF = CONFIG_HOME / 'zorro-thinkpad' / 'config.json'
MAC = re.compile(r'^[0-9A-F]{2}(:[0-9A-F]{2}){5}$')

DEFAULTS = {
    'slices': [                     # 1 to 6 slices, clockwise from the top
        {'name': 'Work', 'categories': ['Office', 'WebBrowser', 'Email', 'Chat',
                                        'InstantMessaging', 'Calendar', 'ContactManagement']},
        {'name': 'Tools', 'categories': ['TerminalEmulator', 'Development', 'TextEditor',
                                         'IDE', 'Debugger', 'RemoteAccess', 'Network']},
        {'name': 'Media', 'categories': ['AudioVideo', 'Audio', 'Video', 'Graphics', 'Player',
                                         'Photography', '3DGraphics', 'Viewer']},
        {'name': 'System', 'categories': ['System', 'Settings', 'Utility', 'FileManager',
                                          'FileTransfer', 'Monitor', 'HardwareSettings']},
    ],
    'ring_slots': [3, 4, 6],        # kept for older configs; the apps float as a cloud now
    'anchor': 'orb',                # orb: around the info circle; bottom-right / bottom-left /
                                    # top-right / top-left: its own clock in that corner; centre
    'size': 1.0,                    # the rings' width (0.7 .. 1.6)
    'icon_size': 1.0,               # the icons (0.7 .. 1.6)
    'notes_hide_vaults': [],        # Obsidian vaults left out of the Notes part (paths)
    'preview_size': 460,            # width of the file preview panel (pixels; height ~ 0.78x)
    'ai_view': 'history',           # the AI part shows: history (what fits) or last (one answer)
    'order': {},                    # slice name -> app ids in the order you dragged them
    'hide': [                       # not in the slices (typing still finds them)
        'thunar-settings.desktop', 'thunar-bulk-rename.desktop', 'rofi.desktop',
        'rofi-theme-selector.desktop', 'kdesystemsettings.desktop', 'systemsettings.desktop',
        'obconf.desktop', 'conky.desktop', 'nm-connection-editor.desktop',
        'com.blackmagicdesign.resolve-CaptureLogs.desktop',
        'com.blackmagicdesign.resolve-Installer.desktop',
        'com.blackmagicdesign.resolve-Panels.desktop',
        'com.blackmagicdesign.rawspeedtest.desktop',
        'com.blackmagicdesign.resolve-DaVinciRemoteMonitoring.desktop',
    ],
    'assign': {                     # app (.desktop name) -> slice name, beats the categories
        'mqttx.desktop': 'Tools', 'kitty.desktop': 'Tools', 'winbox.desktop': 'Tools',
        'localsend_app.desktop': 'Tools', 'org.localsend.localsend_app.desktop': 'Tools',
        'thunar.desktop': 'Work', 'org.gnome.Nautilus.desktop': 'Work', 'nemo.desktop': 'Work',
        'org.kde.dolphin.desktop': 'Work', 'zorro-drive.desktop': 'Work',
        'google-apps.desktop': 'Work', 'whatsapp.desktop': 'Work', 'instagram.desktop': 'Work',
        'linkedin.desktop': 'Work',
        'com.blackmagicdesign.resolve.desktop': 'Media',
        'com.blackmagicdesign.rawplayer.desktop': 'Media',
    },
}


def strings(v):
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def clean_slices(v):
    """the slices that can be drawn: a name and a list of categories each; None when none is left"""
    if not isinstance(v, list):
        return None
    out = []
    for s in v:
        if isinstance(s, dict) and isinstance(s.get('name'), str) and s['name'].strip():
            cats = s.get('categories')
            out.append({**s, 'categories': cats if strings(cats) else []})
    return out or None


def clean_order(v):
    if not isinstance(v, dict):
        return None
    return {k: ids for k, ids in v.items() if isinstance(k, str) and strings(ids)}


def clean_assign(v):
    if not isinstance(v, dict):
        return None
    return {k: s for k, s in v.items() if isinstance(k, str) and isinstance(s, str)}


CLEAN = {       # key -> the value as it can be used, or None: keep the default
    'slices': clean_slices,
    'ring_slots': lambda v: v if isinstance(v, list) and v and all(
        number(x) and x > 0 for x in v) else None,
    'anchor': lambda v: v if isinstance(v, str) else None,
    'size': lambda v: v if number(v) else None,
    'icon_size': lambda v: v if number(v) else None,
    'notes_hide_vaults': lambda v: v if strings(v) else None,
    'preview_size': lambda v: v if number(v) else None,
    'ai_view': lambda v: v if v in ('history', 'last') else None,
    'order': clean_order,
    'hide': lambda v: v if strings(v) else None,
    'assign': clean_assign,
}


def read_json(path):
    """the file as a dict; {} when it is missing, broken or not an object"""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_conf(path=None):
    """the settings: the defaults, with every usable value from the file over them"""
    c = json.loads(json.dumps(DEFAULTS))
    for key, value in read_json(path or CONF).items():
        clean = CLEAN[key](value) if key in CLEAN else None
        if clean is None:
            continue
        if key == 'assign':
            c['assign'].update(clean)
        else:
            c[key] = clean
    return c


def save_keys(**kv):
    """write these config keys, keeping everything else in the config"""
    user = read_json(CONF)
    user.update(kv)
    CONF.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONF.with_suffix('.tmp')
    tmp.write_text(json.dumps(user, indent=2))
    tmp.replace(CONF)


def save_arrangement(order, assign):
    """write the dragged order (and slice moves) into the config, keeping everything else"""
    old = read_json(CONF).get('assign')
    save_keys(order=order, assign={**(old if isinstance(old, dict) else {}), **assign})


def orb_conf():
    """where the info circle is (its size, corner and margin)"""
    c = {'size': 240, 'corner': 'bottom-right', 'margin': 28}
    user = read_json(ORB_CONF)
    for k in ('size', 'margin'):
        if number(user.get(k)) and user[k] > 0:
            c[k] = user[k]
    if isinstance(user.get('corner'), str):
        c['corner'] = user['corner']
    return c


def music_outputs(path=None):
    """the Bluetooth addresses ticked in System → Bluetooth for the Music part's output picker"""
    ticked = read_json(path or THINKPAD_CONF).get('music_outputs')
    if not isinstance(ticked, list):
        return []
    out = []
    for mac in ticked:
        mac = mac.strip().upper() if isinstance(mac, str) else ''
        if MAC.match(mac) and mac not in out:
            out.append(mac)
    return out
