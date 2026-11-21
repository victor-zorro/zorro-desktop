"""The automatic checks. Each returns (ok, detail) and stops at its deadline."""
import json
import subprocess
import sys
import time

from . import devices, paths, store

TIMEOUT = 120       # seconds per check
NO_TESTS = 5        # unittest's exit code for a folder without tests


def left(deadline):
    return max(1, deadline - time.monotonic())


def tracked(repo, deadline):
    done = subprocess.run(['git', 'ls-files'], cwd=repo, capture_output=True, text=True, timeout=left(deadline))
    files = [repo / name for name in done.stdout.splitlines()]
    return [f for f in files if f.is_file() and not f.is_symlink()]


def read(file):
    try:
        return file.read_text()
    except (OSError, UnicodeDecodeError):
        return None


def is_python(file, text):
    return file.suffix == '.py' or (not file.suffix and text.startswith('#!') and 'python' in text.split('\n', 1)[0])


def each_file(repo, deadline, wanted, problem):
    """Run `problem(file, text)` on every wanted file; report the first few problems."""
    bad, count = [], 0
    for file in tracked(repo, deadline):
        if time.monotonic() > deadline:
            return False, f'timed out after {count} files'
        text = read(file)
        if text is None or not wanted(file, text):
            continue
        count += 1
        why = problem(file, text)
        if why:
            bad.append(f'{file.relative_to(repo)}: {why}')
    if bad:
        return False, f'{len(bad)} of {count} files: ' + '; '.join(bad[:3])
    return True, f'{count} files'


def check_rules(repo, deadline):
    """tools/check-rules passes: no file over 400 lines, no function over 60."""
    tool = repo / 'tools' / 'check-rules'
    if not tool.is_file():
        return False, 'tools/check-rules is missing'
    done = subprocess.run([sys.executable, str(tool)], cwd=repo, capture_output=True, text=True, timeout=left(deadline))
    lines = done.stdout.strip().splitlines() or [done.stderr.strip()[-200:]]
    return done.returncode == 0, lines[-1] if done.returncode == 0 else '; '.join(lines[:3])


def check_compile(repo, deadline):
    """Every tracked Python file and Python script compiles."""
    def problem(file, text):
        try:
            compile(text, str(file), 'exec', dont_inherit=True)
        except (SyntaxError, ValueError) as err:
            return f'line {getattr(err, "lineno", "?")}: {getattr(err, "msg", err)}'
    return each_file(repo, deadline, is_python, problem)


def check_shell(repo, deadline):
    """Every tracked .sh file passes bash -n."""
    def problem(file, text):
        done = subprocess.run(['bash', '-n', str(file)], capture_output=True, text=True, timeout=left(deadline))
        return done.stderr.strip().splitlines()[-1] if done.returncode else None
    return each_file(repo, deadline, lambda file, text: file.suffix == '.sh', problem)


def check_json(repo, deadline):
    """Every tracked .json file parses."""
    def problem(file, text):
        try:
            json.loads(text)
        except ValueError as err:
            return str(err)
    return each_file(repo, deadline, lambda file, text: file.suffix == '.json', problem)


def check_units(repo, deadline):
    """python3 -m unittest discover passes in every apps/*/tests folder."""
    folders = sorted(f for f in repo.glob('apps/*/tests') if f.is_dir())
    bad = []
    for folder in folders:
        done = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(folder)],
                              cwd=repo, capture_output=True, text=True, timeout=left(deadline))
        if done.returncode not in (0, NO_TESTS):
            last = (done.stderr.strip().splitlines() or ['failed'])[-1]
            bad.append(f'{folder.relative_to(repo)}: {last}')
    if bad:
        return False, '; '.join(bad[:3])
    return True, f'{len(folders)} test folders'


CHECKS = {'rules': check_rules, 'compile': check_compile, 'shell': check_shell,
          'json': check_json, 'units': check_units}


def run_one(name):
    try:
        ok, detail = CHECKS[name](paths.repo(), time.monotonic() + TIMEOUT)
    except subprocess.TimeoutExpired:
        ok, detail = False, f'timed out after {TIMEOUT} s'
    except OSError as err:
        ok, detail = False, str(err)
    return {'ok': bool(ok), 'detail': str(detail)[:300], 'at': paths.now(), 'version': devices.head()}


def results():
    data = paths.read_json(paths.data_dir() / 'checks.json', {})
    return data if isinstance(data, dict) else {}


def run(names=None):
    """Run the checks, keep the results, and set the test state of the items they prove."""
    names = [n for n in (names or CHECKS) if n in CHECKS]
    new = {name: run_one(name) for name in names}
    device = devices.this_device()
    devices.devices()
    with store.LOCK:
        paths.write_json(paths.data_dir() / 'checks.json', dict(results(), **new))
        changed = 0
        for item in store.all_items():
            result = new.get(item.get('check') or '')
            if result:
                state = 'ok' if result['ok'] else 'fail'
                store.set_test(item['id'], device, state, result['version'], commit_now=False)
                changed += 1
        if changed:
            failed = sum(1 for r in new.values() if not r['ok'])
            store.commit(f'checks: {len(new) - failed} ok, {failed} fail')
    return new
