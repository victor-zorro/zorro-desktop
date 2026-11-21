"""The settings in ~/.config/zorro-ai/config.json: read, check, write (atomic)."""
import json
import os
import tempfile

from . import paths

PLACES = ('dialer', 'intel', 'devs')
ENGINES = ('claude', 'mistral', 'local')
DEFAULTS = {'places': {'dialer': 'auto', 'intel': 'auto', 'devs': 'claude'},
            'local_only': False, 'local_model': None, 'local_model_battery': None}


class BadSetting(ValueError):
    pass


def valid_engine(value):
    """auto, an engine name, or local:<model id>"""
    if value == 'auto' or value in ENGINES:
        return True
    return isinstance(value, str) and value.startswith('local:') and known_model(value[6:])


def known_model(model_id):
    """only models from the catalogue: an id never becomes a path of its own"""
    from . import models
    return any(m.get('id') == model_id for m in models.catalogue())


def load():
    """the saved settings. A setting that is not understood is skipped, the rest still
    counts; a file that cannot be read at all means: nothing leaves this laptop"""
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        saved = json.loads(paths.config_file().read_text())
    except FileNotFoundError:
        return cfg
    except (OSError, ValueError):
        saved = None
    if not isinstance(saved, dict):
        cfg['local_only'] = True
        return cfg
    for key, value in saved.items():
        parts = [{key: {place: engine}} for place, engine in value.items()] \
            if key == 'places' and isinstance(value, dict) else [{key: value}]
        for part in parts:
            try:
                cfg = merged(cfg, part)
            except BadSetting:
                if key == 'local_only':
                    cfg['local_only'] = True
    return cfg


def merged(cfg, changes):
    """cfg with the changes applied; BadSetting when a change is not allowed"""
    out = json.loads(json.dumps(cfg))
    if not isinstance(changes, dict):
        raise BadSetting('set must be an object')
    for key, value in changes.items():
        if key == 'places':
            _merge_places(out['places'], value)
        elif key == 'local_only':
            if not isinstance(value, bool):
                raise BadSetting('local_only must be true or false')
            out[key] = value
        elif key in ('local_model', 'local_model_battery'):
            if value is not None and not (isinstance(value, str) and known_model(value)):
                raise BadSetting(f'{key} must be a model from the list, or null')
            out[key] = value
        else:
            raise BadSetting(f'unknown setting: {key}')
    return out


def _merge_places(places, value):
    if not isinstance(value, dict):
        raise BadSetting('places must be an object')
    for place, engine in value.items():
        if place not in PLACES:
            raise BadSetting(f'unknown place: {place}')
        if not valid_engine(engine):
            raise BadSetting(f'unknown engine for {place}: {engine}')
        places[place] = engine


def save(cfg):
    write_atomic(paths.config_file(), json.dumps(cfg, indent=1) + '\n')


def change(changes):
    """apply the changes and write the file; the new settings"""
    cfg = merged(load(), changes)
    save(cfg)
    return cfg


def write_atomic(path, text, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
