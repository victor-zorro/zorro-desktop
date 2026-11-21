"""red lid dot, power LED, keyboard light, Morse code"""
import os
import sys
import time
from pathlib import Path
from .base import KBD_LED, load_conf, run, sysread
from .power import BAT


# ---- lights: red dot on the lid, power button LED, keyboard light --------------------------
# The udev rule makes brightness + trigger writable for group video, so no root is needed.
# Saved in config.json under "lights"; keyd applies them at login and after every resume
# (the firmware resets the LEDs on resume).

LEDS = Path('/sys/class/leds')
DOT_LED, POWER_LED = LEDS / 'tpacpi::lid_logo_dot', LEDS / 'tpacpi::power'
DOT_MODES = {                       # mode: (label, trigger or None = steady on/off)
    'on': ('On', None),
    'off': ('Off', None),
    'heartbeat': ('Heartbeat pulse', 'heartbeat'),
    'blink': ('Slow blink', 'timer'),
    'charging': ('Blinks while charging, on when full', 'BAT0-charging-blink-full-solid'),
    'ac': ('On only on the charger', 'AC-online'),
    'disk': ('Flickers with disk activity', 'disk-activity'),
    'fast': ('Fast blink', None),                                  # keyd blinks these
    'flash': ('Double flash every 2 seconds', None),
    'morse': ('Morse code: your own word or sentence', None),
}
SOFT_MODES = ('fast', 'flash', 'morse')         # blinked by keyd's dot_loop, not the kernel
# activity overrides for the red dot, most important first; each can pick its own pattern
OVERRIDES = [
    ('message', 'A message arrives (notification on screen)'),
    ('privacy', 'Webcam or microphone in use'),
    ('bat_low', 'Battery low'),
    ('bat_full', 'Battery full (on the charger)'),
    ('charger', 'On the charger'),
]
OVERRIDE_MODES = [('none', 'No change')] + [(k, v[0]) for k, v in DOT_MODES.items()
                                            if k not in ('charging', 'ac')]
BAT_LOW = 15
KBD_LEVELS = {0: 'Off', 1: 'Low', 2: 'High'}


def set_led(led, mode):
    """mode: 'on', 'off' or a DOT_MODES key; returns an error text or None"""
    trig = DOT_MODES.get(mode, ('', None))[1]
    try:
        if trig:
            if trig not in (led / 'trigger').read_text():
                return f'{trig}: not available (run apps/zorro-thinkpad/install.sh)'
            (led / 'trigger').write_text(trig)
        else:
            if '[none]' not in (led / 'trigger').read_text():
                (led / 'trigger').write_text('none')
            mx = (led / 'max_brightness').read_text().strip()
            (led / 'brightness').write_text(mx if mode == 'on' else '0')
    except PermissionError:
        return 'no permission: run sudo apps/zorro-thinkpad/install.sh'
    except OSError as e:
        return f'{led.name}: {e.strerror}'
    return None


def set_kbd(level):
    try:
        (KBD_LED / 'brightness').write_text(str(int(level)))
    except OSError as e:
        return f'keyboard light: {e.strerror}'
    return None



MORSE = {
    'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.', 'G': '--.',
    'H': '....', 'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..', 'M': '--', 'N': '-.',
    'O': '---', 'P': '.--.', 'Q': '--.-', 'R': '.-.', 'S': '...', 'T': '-', 'U': '..-',
    'V': '...-', 'W': '.--', 'X': '-..-', 'Y': '-.--', 'Z': '--..',
    '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-', '5': '.....',
    '6': '-....', '7': '--...', '8': '---..', '9': '----.',
    '.': '.-.-.-', ',': '--..--', '?': '..--..', '!': '-.-.--', '/': '-..-.', '-': '-....-',
    '@': '.--.-.', ':': '---...', "'": '.----.', '=': '-...-', '+': '.-.-.', '&': '.-...',
}
MORSE_TEXT, MORSE_UNIT = 'SOS', 0.15


def morse_timeline(text):
    """[(on, units)]: dot 1, dash 3, gap in a letter 1, between letters 3, between words 7"""
    out = []
    for word in text.upper().split():
        for letter in word:
            code = MORSE.get(letter)
            if not code:
                continue
            for sym in code:
                out += [(True, 1 if sym == '.' else 3), (False, 1)]
            out[-1] = (False, 3)
        if out:
            out[-1] = (False, 7)
    return out


def play_morse(text, unit, keep_going=lambda: True):
    """blink text once on the lid dot; stops early when keep_going() turns False"""
    bright = DOT_LED / 'brightness'
    mx = (DOT_LED / 'max_brightness').read_text().strip()
    for on, units in morse_timeline(text):
        if not keep_going():
            return False
        bright.write_text(mx if on else '0')
        time.sleep(units * unit)
    return True


def on_charger():
    return sysread('/sys/class/power_supply/AC/online', '1') == '1'


_cam = {'at': -1e9, 'val': False}


def camera_or_mic_in_use():
    """shared by the red dot and 'stay awake in calls': one look every 5 s on the charger,
    every 15 s on battery (it walks /proc and asks PipeWire)"""
    if time.monotonic() - _cam['at'] < (5 if on_charger() else 15):
        return _cam['val']
    _cam['val'] = _camera_or_mic_in_use()
    _cam['at'] = time.monotonic()
    return _cam['val']


def _camera_or_mic_in_use():
    for fd_dir in Path('/proc').glob('[0-9]*/fd'):           # our own processes only
        try:
            for fd in fd_dir.iterdir():
                if os.readlink(fd).startswith('/dev/video'):
                    return True
        except OSError:
            pass
    return bool(run('pactl', 'list', 'short', 'source-outputs').strip())


def condition(key, li):
    if key == 'message':
        return run('dunstctl', 'count', 'displayed').strip() not in ('', '0')
    if key == 'privacy':
        return camera_or_mic_in_use()
    if key == 'charger':
        return on_charger()
    status = sysread(BAT / 'status')
    if key == 'bat_full':
        return on_charger() and status in ('Full', 'Not charging')
    if key == 'bat_low':
        try:
            cap = int(sysread(BAT / 'capacity', '100'))
        except ValueError:
            return False
        return not on_charger() and cap <= int(li.get('bat_low_pct', BAT_LOW))
    return False


_dot = {'refresh': False, 'checked': 0.0, 'mode': None, 'conf': None}


def dot_mode():
    """the pattern the red dot should show now: the first active override, else the
    normal one. Conditions are checked at most every 5 seconds, 15 on battery (or at once on a
    settings change)."""
    li = load_conf().get('lights', {})
    if not isinstance(li, dict):
        li = {}
    if li != _dot['conf'] or time.monotonic() - _dot['checked'] > (5 if on_charger() else 15):
        mode = li.get('dot', 'on')
        ov = li.get('overrides', {}) if isinstance(li.get('overrides'), dict) else {}
        for key, _ in OVERRIDES:
            m = ov.get(key, 'none')
            try:
                active = m != 'none' and condition(key, li)
            except (ValueError, TypeError, OSError):
                active = False
            if active:
                mode = m
                break
        _dot.update(conf=li, mode=mode, checked=time.monotonic())
    return _dot['mode'], li


def dot_loop():
    """keyd thread: keeps the red dot on the right pattern and blinks the software ones"""
    current = applied = None
    while True:
        try:
            mode, li = dot_mode()
            # a settings change also re-applies: the app wrote the LED itself meanwhile
            if mode != current or li != applied or _dot['refresh']:
                _dot['refresh'], applied = False, li
                if not li and mode == 'on':
                    current = mode                  # never configured: leave it alone
                else:
                    set_led(DOT_LED, mode)
                    current = mode
            same = lambda: dot_mode() == (mode, li)
            try:
                unit = min(1.0, max(0.05, float(li.get('morse_unit', MORSE_UNIT))))
            except (TypeError, ValueError):
                unit = MORSE_UNIT
            if mode == 'morse':
                if play_morse(li.get('morse_text') or MORSE_TEXT, unit, same):
                    time.sleep(3)
            elif mode == 'fast':
                play_pattern([(True, 0.15), (False, 0.15)] * 7, same)
            elif mode == 'flash':
                play_pattern([(True, 0.1), (False, 0.15), (True, 0.1), (False, 1.65)], same)
            else:
                time.sleep(1)
        except OSError:
            time.sleep(30)                          # no permission yet
        except Exception as e:                      # noqa: BLE001 - never let the dot die
            print(f'zorro-thinkpad dot: {type(e).__name__}: {e}', file=sys.stderr)
            time.sleep(5)


def play_pattern(steps, keep_going):
    bright = DOT_LED / 'brightness'
    mx = (DOT_LED / 'max_brightness').read_text().strip()
    for on, secs in steps:
        if not keep_going():
            return
        bright.write_text(mx if on else '0')
        time.sleep(secs)


def apply_lights():
    li = load_conf().get('lights', {})
    errs = []
    if 'dot' in li:
        errs.append(set_led(DOT_LED, li['dot']))
        _dot['refresh'] = True              # keyd's dot_loop re-applies overrides too
    if 'power' in li:
        errs.append(set_led(POWER_LED, li['power']))
    if li.get('kbd') is not None:
        errs.append(set_kbd(li['kbd']))
    return [e for e in errs if e]
