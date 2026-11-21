"""Run `zorro-ai pull MODEL` or `zorro-ai install-local` and follow its progress lines."""
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

PERCENT = re.compile(r'([\d.]+)\s*MB\s+([\d.]+)%')
SIBLING = Path(os.path.realpath(__file__)).parent.parent.parent / 'zorro-ai' / 'zorro-ai'


def program():
    """the zorro-ai program: on PATH, else the one next to this app in the repo"""
    return shutil.which('zorro-ai') or (str(SIBLING) if SIBLING.is_file() else None)


def fraction(line):
    """0..1 from a progress line ('name:   12.0 MB  40.0%'), None for any other line"""
    found = PERCENT.search(line)
    return min(1.0, float(found.group(2)) / 100) if found else None


def lines_of(chunks):
    """text lines from byte chunks; a carriage return ends a line too (progress redraws one line)"""
    rest = ''
    for chunk in chunks:
        rest += chunk.decode(errors='replace').replace('\r', '\n')
        *whole, rest = rest.split('\n')
        yield from (line for line in whole if line.strip())
    if rest.strip():
        yield rest


class Run:
    """One run of zorro-ai. run() -> (ok, last line said); cancel() ends the program."""

    def __init__(self, args, on_line=lambda line: None, command=None):
        self.args, self.on_line = list(args), on_line
        self.command = command
        self.proc = None
        self.cancelled = threading.Event()

    def run(self):
        command = self.command or program()
        if not command:
            return False, 'zorro-ai is not installed'
        try:
            self.proc = subprocess.Popen([command, *self.args], stdin=subprocess.DEVNULL,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except OSError as e:
            return False, str(e)
        if self.cancelled.is_set():
            self.proc.terminate()
        last = ''
        with self.proc.stdout as out:
            for line in lines_of(iter(lambda: out.read1(4096), b'')):
                self.on_line(line)
                if fraction(line) is None:
                    last = line.strip()
        code = self.proc.wait()
        if self.cancelled.is_set():
            return False, 'Stopped'
        return code == 0, last.removeprefix('zorro-ai: ') or ('Done' if code == 0 else f'failed ({code})')

    def cancel(self):
        self.cancelled.set()
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
