"""System info: this laptop's hardware and how much of it is in use (read only, no root)"""
import json
import os
import re
import time
from pathlib import Path

from .base import run, sysread


def gb(n):
    return f'{n / 1024 ** 3:.1f} GB' if n < 1024 ** 4 else f'{n / 1024 ** 4:.2f} TB'


def meminfo():
    m = {}
    for line in sysread('/proc/meminfo').splitlines():
        k, _, v = line.partition(':')
        m[k] = int(v.split()[0]) * 1024 if v.split() else 0
    return m


def collect():
    dmi = Path('/sys/class/dmi/id')
    info = {'model': f'{sysread(dmi / "sys_vendor")} {sysread(dmi / "product_version")}'.strip(),
            'type': sysread(dmi / 'product_name'), 'bios': sysread(dmi / 'bios_version'),
            'bios_date': sysread(dmi / 'bios_date')}
    cpu = sysread('/proc/cpuinfo')
    m = re.search(r'model name\s*:\s*(.+)', cpu)
    info['cpu'] = m.group(1).strip() if m else '?'
    info['threads'] = os.cpu_count()
    cores = {l for l in re.findall(r'core id\s*:\s*(\d+)', cpu)}
    info['cores'] = len(cores) or info['threads']
    mx = sysread('/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq')
    info['cpu_max'] = f'{int(mx) / 1e6:.1f} GHz' if mx.isdigit() else ''
    vga = next((l.split(': ', 1)[-1] for l in run('lspci').splitlines()
                if re.search(r'VGA|3D|Display', l)), '?')
    info['gpu'] = re.sub(r'\s*\(rev \w+\)', '', vga)
    vram = sysread('/sys/class/drm/card0/device/mem_info_vram_total')
    info['vram'] = gb(int(vram)) if vram.isdigit() else ''
    drv = Path('/sys/class/drm/card0/device/driver')
    info['gpu_driver'] = os.path.basename(os.path.realpath(drv)) if drv.exists() else ''
    mem = meminfo()
    info['mem_total'], info['mem_used'] = mem.get('MemTotal', 0), mem.get('MemTotal', 0) - mem.get('MemAvailable', 0)
    info['swap_total'], info['swap_used'] = mem.get('SwapTotal', 0), mem.get('SwapTotal', 0) - mem.get('SwapFree', 0)
    disks = []
    try:
        tree = json.loads(run('lsblk', '-b', '-J', '-o', 'NAME,SIZE,TYPE,MODEL,TRAN') or '{}')
        for d in tree.get('blockdevices', []):
            if d.get('type') == 'disk' and int(d.get('size') or 0) > 0:
                disks.append({'name': d['name'], 'model': (d.get('model') or '').strip(),
                              'size': int(d['size']), 'bus': d.get('tran') or ''})
    except ValueError:
        pass
    info['disks'] = disks
    mounts = []
    for mp in ('/', '/home', str(Path.home() / 'Drive')):
        try:
            st = os.statvfs(mp)
        except OSError:
            continue
        total, free = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
        if total and all(m['total'] != total for m in mounts):
            mounts.append({'path': mp, 'total': total, 'used': total - free})
    info['mounts'] = mounts
    osr = dict(re.findall(r'^(\w+)="?([^"\n]*)"?', sysread('/etc/os-release'), re.M))
    info['os'] = osr.get('PRETTY_NAME', 'Linux')
    info['kernel'] = os.uname().release
    up = float(sysread('/proc/uptime', '0 0').split()[0])
    info['uptime'] = f'{int(up // 86400)} d {int(up % 86400 // 3600)} h' if up > 86400 else \
        f'{int(up // 3600)} h {int(up % 3600 // 60)} min'
    m = re.search(r'(\d+x\d+)\+\d+\+\d+', run('xrandr', '--current'))
    info['screen'] = m.group(1) if m else ''
    temps = {}
    for h in Path('/sys/class/hwmon').glob('hwmon*'):
        name = sysread(h / 'name')
        t = sysread(h / 'temp1_input')
        if name in ('k10temp', 'amdgpu', 'nvme', 'thinkpad', 'acpitz') and t.lstrip('-').isdigit():
            temps[{'k10temp': 'Processor', 'amdgpu': 'Graphics', 'nvme': 'SSD', 'thinkpad': 'ThinkPad',
                   'acpitz': 'Board'}[name]] = int(t) / 1000
    info['temps'] = temps
    info['time'] = time.time()
    return info
