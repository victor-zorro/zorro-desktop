#!/usr/bin/python3
"""Mark a step of the run in progress.json with the real clock, so times are measured, not
guessed.

  plan/step.py start PREFIX [--est MIN] [--note TEXT]   it starts now (estimated MIN minutes)
  plan/step.py done PREFIX [--note TEXT]                it finished now
  plan/step.py note PREFIX --note TEXT [--pct N]        only the note / percentage
PREFIX is the start of the step's name.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

FILE = Path(__file__).resolve().parent / 'progress.json'


def main():
    args = sys.argv[1:]
    if len(args) < 2 or args[0] not in ('start', 'done', 'note'):
        print(__doc__.strip())
        return 1
    verb, prefix = args[0], args[1]
    opt = {args[i][2:]: args[i + 1] for i in range(2, len(args) - 1, 2) if args[i].startswith('--')}
    data = json.loads(FILE.read_text())
    step = next((s for s in data['steps'] if s['name'].startswith(prefix)), None)
    if not step:
        print('no step starts with:', prefix)
        return 1
    now = datetime.now().strftime('%H:%M')
    if verb == 'start':
        step.update(state='doing', started=now, pct=step.get('pct') or 5)
        if 'est' in opt:
            step.update(est=int(opt['est']), est_at=now)
    elif verb == 'done':
        step.update(state='done', finished=now, pct=100)
    if 'note' in opt:
        step['note'] = opt['note']
    if 'pct' in opt:
        step['pct'] = int(opt['pct'])
    FILE.write_text(json.dumps(data, indent=1, ensure_ascii=False) + '\n')
    print(step['name'], '→', step['state'], now)
    return 0


if __name__ == '__main__':
    sys.exit(main())
