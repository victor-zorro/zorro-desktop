"""login look and theme presets"""
import json
from .base import APPS, CONF


# ---- login / lock screen look ---------------------------------------------------------------

DM_DIR = APPS / 'zorro-dm'
CUSTOM_PRESETS = CONF.parent / 'presets.json'


def theme_presets():
    """the built-in looks (apps/zorro-dm/theme/presets.json)"""
    try:
        return json.loads((DM_DIR / 'theme' / 'presets.json').read_text())
    except (OSError, ValueError):
        return {}


def custom_presets():
    try:
        data = json.loads(CUSTOM_PRESETS.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


WALL_DEFAULTS = {'enabled': True, 'follow_login': True, 'fps_ac': 24, 'fps_battery': 8,
                 'render_scale': 0.5, 'look': {}}
LOOK_FILE = '/etc/zorro-dm/look.json'
_look_draft = {}
LOOK_ANIMALS = {'whale': 'Blue whale', 'vaquita': 'Vaquita (rarest porpoise)',
                'hammerhead': 'Hammerhead shark', 'turtle': 'Leatherback sea turtle',
                'manta': 'Giant manta ray', 'random': 'Random, a different one each time'}
LOOK_DEFAULTS = {
    'animal': 'whale', 'line_colour': '#e6e6ec', 'density': 1.0, 'size': 1.0, 'swim_speed': 1.0,
    'pass_seconds': 70, 'gap_seconds': 0, 'far': 0.33,
    'snow_amount': 140, 'snow_speed': 1.0, 'snow_size': 1.0, 'snow_colour': '#9a9aa0',
    'snow_alpha': 1.0, 'grain': 1.0, 'scratches': 1.0, 'dust': 1.0, 'scanlines': 1.0,
    'vignette': 1.0, 'flicker': 1.0, 'chroma': 1.0, 'glitch_rate': 1.0, 'glitch_strength': 1.0,
    'bars': False, 'crt': False, 'cblur': 1.0, 'cblur_mode': 'lens', 'bloom': 0.6,
    'background': 'deep', 'bg_strength': 1.0, 'bg_speed': 1.0, 'bg_aberration': 1.0,
}
LOOK_BACKGROUNDS = {'deep': 'Deep sea: dark, with pools of iridescent light',
                    'waves': 'Iridescent waves: deep blue with magenta folds',
                    'streaks': 'Light streaks: tall blurred bands of colour',
                    'black': 'Black (the old look)'}
CBLUR_MODES = {'lens': 'Lens: colours fan out from the centre', 'prism': 'Prism: sideways colour smear',
               'glow': 'Glow: soft, with a warm halo'}
