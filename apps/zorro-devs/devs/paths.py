"""Where things live. Read at call time, so tests can point them elsewhere."""
import json
import os
from datetime import datetime
from pathlib import Path


def data_dir():
    base = os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share'
    return Path(base) / 'zorro-devs'


def items_dir():
    return data_dir() / 'items'


def plan_answers():
    base = os.environ.get('XDG_STATE_HOME') or Path.home() / '.local' / 'state'
    return Path(base) / 'zorro-plan' / 'answers.json'


def repo():
    """The zorro-desktop repo this package sits in (apps/zorro-devs/devs/)."""
    return Path(os.environ.get('ZORRO_DEVS_REPO') or Path(__file__).resolve().parents[3])


def now():
    return datetime.now().isoformat(timespec='seconds')


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def write_json(path, data):
    """Atomic: write next to the file, then swap."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    tmp.replace(path)
