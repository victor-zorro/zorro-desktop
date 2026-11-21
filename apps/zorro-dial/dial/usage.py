"""How often each app is started: the more and the more recently, the closer to the clock."""
import json
import os
import time
from pathlib import Path

STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'zorro-dial'
USAGE = STATE / 'usage.json'


def load_usage():
    try:
        u = json.loads(USAGE.read_text())
        return u if isinstance(u, dict) else {}
    except (OSError, ValueError):
        return {}


def record(app_id):
    u = load_usage()
    e = u.get(app_id, {'n': 0, 'last': 0})
    e['n'] = e.get('n', 0) + 1
    e['last'] = time.time()
    u[app_id] = e
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = USAGE.with_suffix('.tmp')
    tmp.write_text(json.dumps(u))
    tmp.replace(USAGE)


def score(u, app_id):
    """starts, with recent ones counting more (half-life two weeks)"""
    e = u.get(app_id)
    if not e:
        return 0.0
    age_days = (time.time() - e.get('last', 0)) / 86400
    return e.get('n', 0) * 0.5 ** (age_days / 14)
