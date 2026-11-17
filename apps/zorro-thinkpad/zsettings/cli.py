"""zorro-thinkpad: Fn keys, on-screen indicator and settings for the ThinkPad T14.

  zorro-thinkpad key NAME   act on a key and show the indicator (Openbox calls this):
                            vol-up vol-down mute mic-mute bright-up bright-down display
                            airplane lte-on lte-off star settings screenshot-region
  zorro-thinkpad keyd       background part, started from Openbox autostart:
                            the indicator window, the keys X cannot see (F4, F9, F10,
                            F11, Fn+PrtSc) and the keyboard light (Fn+Space)
  zorro-thinkpad osd ICON VALUE [TEXT]   show the indicator (testing)
  zorro-thinkpad morse TEXT  blink TEXT once as Morse code on the red lid dot
  zorro-settings [--page SECTION:N]   the Zorro app (e.g. --page power:0)
  zorro-settings --apply-windows [--login]   write window theme, picom, kitty, GTK css

Which key arrives where (measured with ./keytest on a T14 Gen 1 AMD):
  X / Openbox : F1-F3 volume, F5-F6 brightness, F7 display, F8 airplane, F12 star
  keyd (evdev): F4 mic mute, F9, F10/F11 phone keys, Fn+PrtSc  - their codes are above
                255, which X11 cannot deliver
  firmware    : Fn+Space keyboard light (keyd only shows the new level)
"""
import sys
import time
from .base import load_conf, osd
from .keys import KEYS
from .lights import DOT_LED, MORSE_UNIT, apply_lights, play_morse, set_led


# ---- main --------------------------------------------------------------------------------

def main():
    a = sys.argv[1:]
    if a[:1] == ['key'] and len(a) == 2 and a[1] in KEYS:
        KEYS[a[1]]()
    elif a[:1] == ['keyd']:
        from .keyd import cmd_keyd          # imported when needed: a key press stays fast
        cmd_keyd()
    elif a[:1] == ['morse'] and len(a) >= 2:                # blink once, e.g. zmorse
        set_led(DOT_LED, 'off')
        time.sleep(1)
        play_morse(' '.join(a[1:]), MORSE_UNIT)
        if 'dot' in load_conf().get('lights', {}):
            apply_lights()
        else:
            set_led(DOT_LED, 'on')
    elif a[:1] == ['osd'] and len(a) >= 3:
        osd(a[1], None if a[2] == '-' else int(a[2]), ' '.join(a[3:]))
    elif not a:
        from .app import cmd_app
        cmd_app()
    elif a[:1] == ['--page'] and len(a) == 2:      # e.g. zorro-settings --page power:0
        from .app import cmd_app
        cmd_app(a[1])
    elif a[:1] == ['--apply-windows']:            # theme, compositor, kitty (autostart: --login)
        from .windows import apply_windows
        apply_windows(login='--login' in a)
    else:
        print(__doc__.strip())
        sys.exit(1)
