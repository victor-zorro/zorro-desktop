"""The window's pages in a private test screen (Xvfb; skipped without it): only the Send page
keeps the sender alive, and its timer never dies on odd numbers."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
XVFB = os.environ.get('XVFB') or shutil.which('Xvfb')
DISPLAY = os.environ.get('ZT_DISPLAY', ':105')


@unittest.skipUnless(XVFB and shutil.which('dbus-run-session'), 'needs Xvfb and dbus-run-session')
class Window(unittest.TestCase):
    def test_pages(self):
        home = Path(tempfile.mkdtemp(prefix='zt-window-'))
        self.addCleanup(shutil.rmtree, home, True)
        run = home / 'run'
        run.mkdir(mode=0o700)
        env = {k: v for k, v in os.environ.items()
               if k not in ('DISPLAY', 'WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS')}
        env.update(HOME=str(home), XDG_RUNTIME_DIR=str(run), DISPLAY=DISPLAY, GDK_BACKEND='x11',
                   XDG_STATE_HOME=str(home / 'state'), XDG_DATA_HOME=str(home / 'data'),
                   XDG_CONFIG_HOME=str(home / 'config'), NO_AT_BRIDGE='1',
                   PATH=f'{HERE}/bin:/usr/bin:/bin', ZORRO_TRANSFER_PORT='1')
        screen = subprocess.Popen([XVFB, DISPLAY, '-screen', '0', '1280x800x24', '-nolisten', 'tcp'],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(1)
            out = subprocess.run(['dbus-run-session', sys.executable, str(HERE / 'window_run.py')],
                                 env=env, capture_output=True, text=True, timeout=60)
        finally:
            screen.terminate()
            screen.wait(5)
        lines = [x for x in out.stdout.splitlines() if x.startswith('{')]
        self.assertTrue(lines, out.stderr[-2000:])
        for what, ok in json.loads(lines[-1]).items():
            self.assertTrue(ok, what)
