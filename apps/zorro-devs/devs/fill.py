"""The first fill of the catalogue from the repo. Safe to run again: an item that is
already there, changed by the user or not, is never touched."""
from . import checks, fill_plan, fill_readme, store

CHECK_TITLES = {'rules': 'Check: build rules hold', 'compile': 'Check: Python files compile',
                'shell': 'Check: shell scripts parse', 'json': 'Check: JSON files parse',
                'units': 'Check: unit tests pass'}


def check_items():
    """One item per automatic check, so its result shows as this device's test."""
    out = []
    for name in checks.CHECKS:
        fields = {'app': 'DEVS', 'category': 'Checks', 'status': 'done', 'check': name,
                  'text': (checks.CHECKS[name].__doc__ or '').strip(),
                  'steps': f'zorro-devs check {name}'}
        out.append(store.new_item('feature', CHECK_TITLES.get(name, f'Check: {name}'), fields))
    return out


def wanted():
    return fill_readme.items() + fill_plan.items() + check_items()


def fill():
    """Write the items that are not there yet. Returns (made, kept)."""
    made = kept = 0
    with store.LOCK:
        for item in wanted():
            if store.path(item['id']).exists():
                kept += 1
                continue
            store.save(item, '', commit_now=False)
            made += 1
        if made:
            store.commit(f'fill: {made} items from the repo')
    return made, kept
