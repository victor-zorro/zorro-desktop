"""Connect → New device: the three ways to start a new machine (the one-line command, a
USB stick, an ISO file), and the NetBird link that lets devices reach each other anywhere."""
import os
import shutil
import subprocess

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .base import APPS, HOME, run
from .ui import Pages, button, combo, form, heading, in_bg, note

REPO = APPS.parent
BOOTSTRAP = ('sudo apt install -y curl && curl -fsSL '
             'https://raw.githubusercontent.com/victor-zorro/zorro-desktop/main/bootstrap.sh | bash')
MAKE_ISO = REPO / 'tools' / 'make-iso'
ISO = HOME / 'Installers' / 'zorro-desktop.iso'


def sticks():
    """USB sticks that are plugged in: {device: 'name, size'}"""
    out = {}
    for line in run('lsblk', '-dnpo', 'NAME,TRAN,RM,SIZE,MODEL').splitlines():
        p = line.split(None, 4)
        if len(p) >= 4 and p[1] == 'usb':
            out[p[0]] = f'{p[4].strip() if len(p) > 4 else "USB stick"}, {p[3]}'
    return out


class ConnectPages:
    def newdevice_page(self):
        box = Pages()
        box.add(heading('One-line command', 'Command'))
        box.add(note('On a fresh Debian 13 or Ubuntu 24.04: open a terminal, paste this line.'))
        line = Gtk.Label(label=BOOTSTRAP, selectable=True, wrap=True, xalign=0)
        line.get_style_context().add_class('monospace')
        box.add(line)
        box.add(button('Copy', self.boot_copy, halign=Gtk.Align.START))
        box.add(note('It installs the desktop. After that: Connect → Transfer on both devices.'))

        box.add(heading('Installer file (ISO)', 'ISO file'))
        box.add(note('A Debian installer that sets up this desktop by itself: boot from it, answer '
                     'name and password, the rest runs alone. Needs the internet while installing.'))
        box.add(button('Make the ISO file', self.iso_make, primary=True, halign=Gtk.Align.START))
        self.iso_msg = note(f'Ready: {ISO}' if ISO.exists() else 'Not made yet (about 1 GB, a few minutes).')
        box.add(self.iso_msg)

        box.add(heading('USB stick', 'USB stick'))
        box.add(note('Writes the ISO file to a stick. Everything on the stick is erased.'))
        self.usb_pick = combo(sticks() or {'': 'No USB stick found'}, '', lambda v: None)
        self.usb_pick.set_active(0)
        box.add(form([('Stick', self.usb_pick)]))
        row = Gtk.Box(spacing=8)
        row.add(button('Look again', self.usb_refresh))
        row.add(button('Write the stick', self.usb_write, primary=True))
        box.add(row)
        self.usb_msg = note()
        box.add(self.usb_msg)
        return box

    def boot_copy(self):
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(BOOTSTRAP, -1)

    def iso_make(self):
        if not os.access(MAKE_ISO, os.X_OK):
            self.iso_msg.set_text('The ISO maker is missing in this copy of the repo.')
            return
        self.iso_msg.set_text('Making the ISO file… (downloads the Debian installer the first time)')

        def work():
            try:
                r = subprocess.run([str(MAKE_ISO), str(ISO)], capture_output=True, text=True, timeout=3600)
                last = (r.stdout + r.stderr).strip().splitlines()[-1:] or ['']
                msg = f'Ready: {ISO}' if r.returncode == 0 else f'Not made: {last[0]}'
            except (OSError, subprocess.TimeoutExpired) as e:
                msg = f'Not made: {e}'
            GLib.idle_add(self.iso_msg.set_text, msg)
        in_bg(work)

    def usb_refresh(self):
        self.usb_pick.remove_all()
        for dev, text in (sticks() or {'': 'No USB stick found'}).items():
            self.usb_pick.append(dev, f'{text}  ({dev})' if dev else text)
        self.usb_pick.set_active(0)

    def usb_write(self):
        dev = self.usb_pick.get_active_id()
        if not dev:
            self.usb_msg.set_text('Plug in a USB stick and press Look again.')
            return
        if not ISO.exists():
            self.usb_msg.set_text('Make the ISO file first.')
            return
        if getattr(self, 'usb_sure', None) != dev:
            self.usb_sure = dev         # asks once: this cannot be undone
            self.usb_msg.set_text(f'This erases {self.usb_pick.get_active_text()}. Press Write the stick again to go on.')
            return
        self.usb_sure = None
        self.usb_msg.set_text('Writing… (your password; a few minutes)')

        def work():
            helper = '/usr/local/libexec/zorro-usb-helper'
            if not (os.access(helper, os.X_OK) and shutil.which('pkexec')):
                msg = 'Needs the helper once, in a terminal: sudo ~/zorro-desktop/apps/zorro-thinkpad/install.sh'
            else:
                try:
                    r = subprocess.run(['pkexec', helper, 'write', str(ISO), dev],
                                       capture_output=True, text=True, timeout=3600)
                    msg = ('The stick is ready: boot the new device from it.' if r.returncode == 0 else
                           'Cancelled' if r.returncode in (126, 127) else
                           (r.stderr.strip().splitlines() or ['failed'])[-1])
                except (OSError, subprocess.TimeoutExpired) as e:
                    msg = f'Not written: {e}'
            GLib.idle_add(self.usb_msg.set_text, msg)
        in_bg(work)

    def netbird_link_page(self):
        box = Pages()
        box.add(heading('NetBird', 'NetBird'))
        box.add(note('NetBird links your devices wherever they are: Transfer then also works '
                     'outside the home network. It is set up under System → Network.'))
        box.add(button('Open the NetBird page', lambda: self.show_page('nb:0'), halign=Gtk.Align.START))
        return box
