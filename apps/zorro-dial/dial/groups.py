"""Which app goes into which slice, and in what order."""
from .config import DEFAULTS
from .usage import score

SETTINGS_CATS = {'Settings', 'DesktopSettings', 'HardwareSettings', 'X-XFCE-SettingsDialog',
                 'X-GNOME-NetworkSettings', 'X-GNOME-Utilities'}
ZORRO = 'zorro-settings.desktop'
GEAR = {'id': '__gear__', 'name': 'Settings', 'icon': 'lucide:settings', 'gear': True}


def hidden_ids(conf, all_apps):
    hidden = set(conf.get('hide', []))
    if any(a['id'] == 'nemo.desktop' for a in all_apps):
        hidden.add('thunar.desktop')        # one file manager in the slices: Nemo
    return hidden


def slice_of(app, slices, names, assign):
    pick = assign.get(app['id'])
    if pick in names:
        return names.index(pick)
    return next((i for i, s in enumerate(slices)
                 if any(c in s['categories'] for c in app['cats'])), len(slices) - 1)


def settings_apps(all_apps, mine):
    """all settings apps (behind the gear): Zorro first, the others by name"""
    rest = sorted((a for a in all_apps if a['id'] != ZORRO and SETTINGS_CATS & set(a['cats'])
                   and a['id'] not in mine), key=lambda a: a['name'].lower())
    zorro = [a for a in all_apps if a['id'] == ZORRO and a['id'] not in mine]
    return zorro + rest


def arrange(conf, all_apps, usage):
    """(groups, settings): per slice its apps, your dragged order first, then by usage (most
    used inward); the settings apps sit behind one gear"""
    slices = conf['slices'][:6]
    names = [s['name'] for s in slices]
    hidden = hidden_ids(conf, all_apps)
    assign = conf.get('assign', {})
    settings = settings_apps(all_apps, hidden - set(DEFAULTS['hide']))
    groups = [[] for _ in slices]
    for a in all_apps:
        is_settings = a['id'] != ZORRO and SETTINGS_CATS & set(a['cats'])
        if not is_settings and a['id'] not in hidden:
            groups[slice_of(a, slices, names, assign)].append(a)
    if settings and groups and '__gear__' not in hidden:
        pick = assign.get('__gear__')                   # the gear: like an app
        groups[names.index(pick) if pick in names else len(groups) - 1].append(dict(GEAR))
    out = []
    for s, g in zip(slices, groups):
        pinned = conf.get('order', {}).get(s['name'], [])
        byid = {a['id']: a for a in g}
        first = [byid[i] for i in pinned if i in byid]
        rest = sorted((a for a in g if a['id'] not in pinned),
                      key=lambda a: (not a.get('gear'), -score(usage, a['id']), a['name'].lower()))
        out.append(first + rest)
    return out, settings


def matches(all_apps, usage, text):
    """the apps that have the typed text: names that start with it first, then by usage"""
    f = text.lower()
    found = [a for a in all_apps if f in a['name'].lower() or f in a['keywords'].lower()
             or f in a['id'].lower()]
    return sorted(found, key=lambda a: (not a['name'].lower().startswith(f),
                                        -score(usage, a['id']), a['name'].lower()))
