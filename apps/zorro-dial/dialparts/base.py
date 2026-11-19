"""shared by the parts: running commands, tiles, the Part class"""
# flake8: noqa: F401 - the parts import their standard modules from here
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

HOME = Path.home()
APPS = Path(os.path.realpath(__file__)).parent.parent.parent      # apps/
MODES = [('apps', 'Apps', 'layout-grid'), ('music', 'Music', 'music'),
         ('notes', 'Notes', 'file-pen'), ('messages', 'Messages', 'bell'),
         ('system', 'System', 'gauge'), ('files', 'Files', 'folder')]


def run(*cmd, timeout=5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ''


def spawn(*cmd):
    try:
        subprocess.Popen(cmd, start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def tile(icon, name, sub='', act=None, **kw):
    return {'tile': True, 'icon': icon, 'name': name, 'sub': sub, 'act': act, **kw}


def ago(seconds):
    s = max(0, int(seconds))
    if s < 90:
        return 'now'
    if s < 3600:
        return f'{s // 60} min'
    if s < 86400:
        return f'{s // 3600} h'
    return f'{s // 86400} d'


class Part:
    key = title = ''

    def __init__(self):
        self.ready = False

    def fetch(self):
        """slow work, in a thread"""
        self.ready = True

    def preview(self):
        return self.title.upper(), self.title, []

    def rings(self):
        return [[], [], []]

    def centre(self):
        """the hub centre clicked while this part is kept: (label shown, callable) or None"""
        return None
