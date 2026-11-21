"""Start one of the two user services Intelligence leans on."""
import subprocess

AI = 'zorro-ai.service'
SEARCH = 'zorro-search.service'


def start(unit, run=subprocess.run):
    """(started, what to tell the user)"""
    try:
        done = run(['systemctl', '--user', 'start', unit], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f'Could not start it: {e}'
    if done.returncode == 0:
        return True, 'Started'
    lines = (done.stderr or '').strip().splitlines()
    return False, 'Could not start it: ' + (lines[-1] if lines else f'systemctl said {done.returncode}')
