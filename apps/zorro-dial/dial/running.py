"""Is a Dialer running already? Asked before GTK is loaded, so a Super press stays fast."""
import os
import signal
from pathlib import Path

RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp'))
DAEMON_PID = RUNTIME / 'zorro-dial-daemon.pid'
PIDFILE = RUNTIME / 'zorro-dial.pid'


def signal_daemon():
    """Super pressed with 'zorro-dial --daemon' running (started at login): it shows or hides
    the dial, already loaded, so this process ends before GTK is even imported"""
    try:
        pid = int(DAEMON_PID.read_text())
        argv = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        if b'--daemon' not in argv or not any(os.path.basename(a) == b'zorro-dial' for a in argv):
            return False
        os.kill(pid, signal.SIGUSR1)
        return True
    except (OSError, ValueError):
        return False


def toggle_running():
    """already open: close it and stop (Super pressed again)"""
    try:
        pid = int(PIDFILE.read_text())
        # a pid file left by a Dialer that died: that number may belong to anything now
        argv = [os.path.basename(x) for x in Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')]
        if not (argv[:1] == [b'zorro-dial'] or
                (argv[0].startswith(b'python') and argv[1:2] == [b'zorro-dial'])):
            return False
        os.kill(pid, signal.SIGTERM)
        return True
    except (OSError, ValueError):
        return False


def remove_pid(file):
    try:
        if file.read_text() == str(os.getpid()):
            file.unlink()
    except OSError:
        pass
