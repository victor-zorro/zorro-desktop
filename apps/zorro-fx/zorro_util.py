"""Small helpers several Zorro apps share (standard library only, so it costs nothing to import).

  import sys; sys.path.insert(0, '<repo>/apps/zorro-fx')
  from zorro_util import vaults, read_json, write_json

Apps that must keep working without this file keep a fallback of their own.
"""
import json
import os
import tempfile
from pathlib import Path

HOME = Path.home()
OBSIDIAN_JSON = HOME / '.config/obsidian/obsidian.json'


def read_json(path, default=None):
    """the file's JSON, or default when it is missing or broken"""
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def write_json(path, data, indent=1):
    """write via a unique temp file + rename, so a reader never sees half a file"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.')
    try:
        with os.fdopen(fd, 'w') as fh:
            json.dump(data, fh, indent=indent)
            fh.write('\n')
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def vault_entries():
    """Obsidian's own list of vaults: [{'path', 'ts', 'open'?}], only those that exist,
    the open one first, then by name"""
    vs = (read_json(OBSIDIAN_JSON, {}) or {}).get('vaults', {})
    vs = [v for v in vs.values() if isinstance(v, dict) and os.path.isdir(v.get('path', ''))]
    vs.sort(key=lambda v: (not v.get('open'), os.path.basename(v['path']).lower()))
    return vs


def vaults():
    """the vault folders as Paths (the open one first)"""
    return [Path(v['path']) for v in vault_entries()]
