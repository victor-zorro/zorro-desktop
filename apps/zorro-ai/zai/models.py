"""The local models: the catalogue (models.json), what is downloaded, and which one to use now."""
import json
from pathlib import Path

from . import paths
from .config import write_atomic

CATALOGUE = Path(__file__).with_name('models.json')
POWER = Path('/sys/class/power_supply')


def catalogue():
    return json.loads(CATALOGUE.read_text())


def find(model_id):
    for m in catalogue():
        if m['id'] == model_id:
            return m
    return None


def model_path(model_id):
    return paths.models_dir() / f'{model_id}.gguf'


def installed(model_id):
    return model_path(model_id).is_file()


def on_battery(power=None):
    """True when a charger is known and none is plugged in"""
    chargers = []
    for supply in sorted((power or POWER).glob('*')):
        try:
            if (supply / 'type').read_text().strip() == 'Battery':
                continue
            chargers.append((supply / 'online').read_text().strip() == '1')
        except OSError:
            continue
    return bool(chargers) and not any(chargers)


def chosen(cfg, forced=None):
    """The model id to use: forced, else the setting for this power state, else the smallest downloaded."""
    if forced:
        return forced
    wanted = cfg.get('local_model')
    if on_battery() and cfg.get('local_model_battery'):
        wanted = cfg['local_model_battery']
    if wanted:
        return wanted
    for m in sorted(catalogue(), key=lambda m: m['size_gb']):
        if installed(m['id']):
            return m['id']
    return None


def speeds():
    try:
        return json.loads(paths.speeds_file().read_text())
    except (OSError, ValueError):
        return {}


def note_speed(model_id, words_per_second):
    known = speeds()
    known[model_id] = round(words_per_second, 1)
    write_atomic(paths.speeds_file(), json.dumps(known, indent=1) + '\n', 0o644)


def listing():
    """what the `models` op answers"""
    measured = speeds()
    out = []
    for m in catalogue():
        speed = measured.get(m['id'])
        out.append({'id': m['id'], 'name': m['name'], 'family': m['family'], 'size': m['size_gb'],
                    'ram': m['ram_gb'], 'good_for': m['good_for'], 'installed': installed(m['id']),
                    'speed': f'{speed} words/s on this laptop' if speed else 'not measured yet'})
    return out
