"""The one Zorro look: colours and font for every app (no other imports, so it costs nothing).

  import sys; sys.path.insert(0, '<repo>/apps/zorro-fx')
  from zorro_style import FG, DIM, RED, CYAN, FONT

Colours are (r, g, b) floats for cairo; HEX has the same as '#rrggbb' for CSS and Pango markup.
The login / lock screen (apps/zorro-dm/theme/style.css) uses the same values as CSS variables;
keep the two in step.
"""

BG = (0.020, 0.027, 0.039)      # #05070a  window background (the login page itself is #000)
FG = (0.847, 0.847, 0.871)      # #d8d8de  text
DIM = (0.435, 0.439, 0.475)     # #6f7079  captions, hints, "off"
LINE = (1.0, 1.0, 1.0)          # thin edges, used at low alpha (CSS: rgba(255,255,255,.16))
RED = (1.0, 0.165, 0.290)       # #ff2a4a  warnings, the left half of the glitch split
CYAN = (0.098, 0.902, 1.0)      # #19e6ff  "on", selection, the right half of the split
GREEN = (0.30, 1.0, 0.62)       # only for "done" in games (Sweep notes' sorted pips)
GREY = (0.60, 0.60, 0.63)       # particles
WHITE = (0.94, 0.94, 0.96)      # particles, bright

FONT = 'DejaVu Sans Mono'       # the theme's font; DejaVu Sans where mono is too wide
FONT_SANS = 'DejaVu Sans'

SPLIT_ALPHA = 0.5               # the red / cyan glitch split behind text: alpha and offset (px)
SPLIT_PX = 1.4


def hexc(rgb):
    return '#' + ''.join(f'{round(c * 255):02x}' for c in rgb)


HEX = {name: hexc(v) for name, v in dict(BG=BG, FG=FG, DIM=DIM, RED=RED, CYAN=CYAN,
                                         GREEN=GREEN, GREY=GREY, WHITE=WHITE).items()}

# status marks (Pango markup): on = cyan, warning = red, off = dim
MARKS = {'on': ('●', HEX['CYAN']), 'ok': ('✓', HEX['CYAN']), 'warn': ('⚠', HEX['RED']),
         'off': ('○', HEX['DIM'])}


def mark(state, symbol=None):
    """a coloured status mark for a Gtk.Label with markup: mark('on'), mark('warn')"""
    sym, col = MARKS.get(state, MARKS['off'])
    return f'<span foreground="{col}">{symbol or sym}</span>'
