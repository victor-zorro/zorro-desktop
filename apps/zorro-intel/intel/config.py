"""The settings in ~/.config/zorro-intel/config.json: the folders the AI may read, excerpts per question."""
import os

from . import files, paths

MAX_EXCERPTS = 8
DEFAULT_EXCERPTS = 4


def load():
    saved = files.read_json(paths.config_file(), {})
    saved = saved if isinstance(saved, dict) else {}
    folders = saved.get('folders')
    folders = [f for f in folders if isinstance(f, str) and f] if isinstance(folders, list) else []
    return {'folders': folders, 'excerpts': _count(saved.get('excerpts', DEFAULT_EXCERPTS))}


def _count(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return DEFAULT_EXCERPTS
    return max(0, min(MAX_EXCERPTS, int(value)))


def save(cfg):
    files.write_json(paths.config_file(), cfg)
    return cfg


def add_folder(path):
    """the settings with this folder added (once)"""
    cfg = load()
    path = os.path.abspath(os.path.expanduser(path))
    if path not in cfg['folders']:
        cfg['folders'].append(path)
        save(cfg)
    return cfg


def remove_folder(path):
    cfg = load()
    cfg['folders'] = [f for f in cfg['folders'] if f != path]
    return save(cfg)


def set_excerpts(count):
    cfg = load()
    cfg['excerpts'] = _count(count)
    return save(cfg)
