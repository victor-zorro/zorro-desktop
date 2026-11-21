"""Whichever media player plays now (MPRIS on the session bus)."""
import sys


def mpris_players():
    """[(bus name, props)] of the media players on the session bus"""
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        names = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                              'ListNames', None, None, 0, 1000, None).unpack()[0]
    except Exception:                   # noqa: BLE001 - no bus: no players
        return []
    out = []
    for n in names:
        if not n.startswith('org.mpris.MediaPlayer2.'):
            continue
        try:
            props = bus.call_sync(n, '/org/mpris/MediaPlayer2', 'org.freedesktop.DBus.Properties', 'GetAll',
                                  GLib.Variant('(s)', ('org.mpris.MediaPlayer2.Player',)),
                                  None, 0, 500, None).unpack()[0]
            out.append((n, props))
        except Exception:               # noqa: BLE001 - a player that does not answer
            continue
    return out


def mpris_call(name, method):
    try:
        from gi.repository import Gio
        Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
            name, '/org/mpris/MediaPlayer2', 'org.mpris.MediaPlayer2.Player', method, None, None, 0, 2000, None)
    except Exception as e:              # noqa: BLE001 - the player went away: say so in the log
        print(f'zorro-dial: {name} {method}: {e}', file=sys.stderr)


def now_playing():
    """the player that plays (else one that is paused): {player, title, artist, playing, pos,
    dur, app}, or None"""
    players = sorted(mpris_players(), key=lambda p: (p[1].get('PlaybackStatus') != 'Playing', 'mpv' not in p[0]))
    for name, props in players:
        md = props.get('Metadata') or {}
        if not md.get('xesam:title') and props.get('PlaybackStatus') == 'Stopped':
            continue
        artist = md.get('xesam:artist') or ['']
        return {'player': name, 'title': md.get('xesam:title') or 'Playing',
                'artist': artist[0] if artist else '', 'playing': props.get('PlaybackStatus') == 'Playing',
                'pos': (props.get('Position') or 0) / 1e6, 'dur': (md.get('mpris:length') or 0) / 1e6,
                'app': name.split('.')[3].split('_')[0]}
    return None
