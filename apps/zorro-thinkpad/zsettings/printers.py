"""printers: what is installed, discovery on the network, adding with the right driver

Uses CUPS's own tools; members of the lpadmin group may add and remove printers without
a password. Discovery: Bonjour / AirPrint announcements (dnssd) and SNMP (printers that
only answer that). The driver: driverless (IPP Everywhere) when the printer speaks IPP,
else the best match CUPS knows for the printer's device ID (e.g. brlaser for Brother
GDI lasers), else a hint which package to install.
"""
import os
import re
import shutil
import socket
from urllib.parse import unquote

from .base import run

LPADMIN, LPINFO = '/usr/sbin/lpadmin', '/usr/sbin/lpinfo'
TESTPAGE = '/usr/share/cups/data/testprint'
DRIVER_HINTS = {                     # maker -> Debian package with open-source drivers
    'brother': 'printer-driver-brlaser', 'hp': 'hplip', 'hewlett-packard': 'hplip',
    'samsung': 'printer-driver-splix', 'xerox': 'printer-driver-foo2zjs',
    'canon': 'printer-driver-gutenprint', 'epson': 'printer-driver-gutenprint',
}


def available():
    return all(shutil.which(p) for p in ('lpstat', 'lp')) and \
        all(os.access(p, os.X_OK) for p in (LPADMIN, LPINFO))


def installed():
    """[{name, uri, state, default}] from lpstat"""
    uris = dict(re.findall(r'^device for (\S+): (\S+)', run('lpstat', '-v'), re.M))
    states = {}
    for line in run('lpstat', '-p').splitlines():
        m = re.match(r'printer (\S+) (?:is )?(\w+)', line)
        if m:
            states[m.group(1)] = 'disabled' if 'disabled' in line else m.group(2)
    m = re.search(r'destination: (\S+)', run('lpstat', '-d'))
    default = m.group(1) if m else ''
    return [{'name': n, 'uri': u, 'state': states.get(n, '?'), 'default': n == default}
            for n, u in uris.items()]


def _rank(uri):
    """which address to keep for one printer: Bonjour names survive a new IP address"""
    if uri.startswith('dnssd://') and ('._ipp' in uri or '._ipps' in uri):
        return 0
    if uri.startswith('dnssd://'):
        return 1
    if uri.startswith(('ipp://', 'ipps://')):
        return 2
    if uri.startswith('socket://'):
        return 3
    return 4


def discover(timeout=8):
    """printers on the network, one entry per printer (best address first), not yet added"""
    out = run(LPINFO, '-l', '--timeout', str(timeout), '--include-schemes', 'dnssd,snmp', '-v',
              timeout=timeout + 15)
    found = []
    for block in re.split(r'^Device: ', out, flags=re.M)[1:]:
        f = {}
        for line in block.splitlines():
            k, sep, v = line.strip().partition(' = ')
            if sep:
                f[k] = v.strip()
        if f.get('uri'):
            found.append({'uri': f['uri'], 'model': f.get('make-and-model') or f.get('info', ''),
                          'info': f.get('info', ''), 'device_id': f.get('device-id', ''),
                          'location': f.get('location', '')})
    have = {p['uri'] for p in installed()}
    best = {}
    for p in sorted(found, key=lambda p: _rank(p['uri'])):
        key = p['model'] or p['uri']
        if p['uri'] in have:
            best[key] = None                        # this printer is already added
        best.setdefault(key, p)
    return [p for p in best.values() if p]


def probe_address(host):
    """a printer at an IP address or host name typed by hand: model and device ID via SNMP
    (like CUPS's own search), driverless only when the printer really accepts a driverless
    format, else its raw port 9100 or LPD with a matching driver"""
    host = host.strip()
    if not re.fullmatch(r'[\w.:-]+', host or ''):
        return None, 'Type an IP address or a host name'

    def port_open(port):
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            return False
    model, device_id = host, ''
    snmp = run('/usr/lib/cups/backend/snmp', host, timeout=20)
    m = re.search(r'^\S+ \S+ "([^"]*)" "[^"]*" "([^"]*)"', snmp, re.M)
    if m:
        model, device_id = m.group(1) or host, m.group(2)
    if port_open(631):
        for path in ('ipp/print', 'ipp', ''):
            uri = f'ipp://{host}/{path}'.rstrip('/')
            attrs = run('ipptool', '-T', '5', '-tv', uri, 'get-printer-attributes.test', timeout=12)
            fmts = re.search(r'document-format-supported \(.*?\) = (.*)', attrs)
            if '[PASS]' in attrs and fmts and re.search(r'pwg-raster|image/urf|application/pdf',
                                                         fmts.group(1)):
                mm = re.search(r'printer-make-and-model \(textWithoutLanguage\) = (.*)', attrs)
                return {'uri': uri, 'model': mm.group(1).strip() if mm else model,
                        'device_id': device_id, 'ipp': True}, ''
    for port, uri in ((9100, f'socket://{host}:9100'), (515, f'lpd://{host}/BINARY_P1')):
        if port_open(port):
            return {'uri': uri, 'model': model, 'device_id': device_id, 'ipp': False}, ''
    return None, f'No printer answers at {host} (is it switched on and on this network?)'


def speaks_ipp(p):
    """driverless: checked for typed addresses; for announced printers, an _ipp service"""
    if 'ipp' in p:
        return p['ipp']
    return '._ipp' in p['uri'] or '._ipps' in p['uri']


def driver_for(p):
    """(model for lpadmin -m, description) or (None, hint)"""
    if speaks_ipp(p):
        return 'everywhere', 'driverless (IPP Everywhere)'
    if p.get('device_id'):
        out = run(LPINFO, '--device-id', p['device_id'], '-m', timeout=30)
        for line in out.splitlines():
            ppd, _, desc = line.partition(' ')
            if ppd and 'everywhere' not in ppd and 'pwgrast' not in ppd \
                    and not desc.lower().startswith('generic'):
                return ppd, desc.strip()
    # by maker and model family: "Brother HL-1210W series" -> brlaser's "HL-1200 series"
    words = (p.get('model') or '').split()
    m = re.search(r'([A-Z]+)-?(\d{2})\d*', p.get('model') or '')
    if words and m:
        family = re.compile(rf'\b{m.group(1)}-?{m.group(2)}\d*', re.I)
        exact = (p.get('model') or '').split(' series')[0].lower()
        hits = []
        for line in run(LPINFO, '-m', timeout=30).splitlines():
            ppd, _, desc = line.partition(' ')
            if desc.lower().startswith(words[0].lower()) and family.search(desc):
                hits.append((exact not in desc.lower(), 'lsb/' in ppd, ppd, desc))
        if hits:
            _, _, ppd, desc = min(hits)
            return ppd, desc.strip()
    maker = words[0].lower() if words else ''
    pkg = DRIVER_HINTS.get(maker)
    return None, (f'This printer needs a driver: sudo apt install {pkg}, then search again'
                  if pkg else 'This printer needs a driver from its maker')


def queue_name(p):
    base = p.get('model') or unquote(p['uri'].split('//')[-1].split('.')[0])
    name = re.sub(r'[^A-Za-z0-9_-]+', '_', base).strip('_')[:40] or 'Printer'
    taken = {q['name'] for q in installed()}
    n, i = name, 2
    while n in taken:
        n, i = f'{name}_{i}', i + 1
    return n


def add(p):
    """add the printer; the first printer also becomes the default. Returns a message."""
    model, desc = driver_for(p)
    if not model:
        return False, desc
    name = queue_name(p)
    out = run(LPADMIN, '-p', name, '-E', '-v', p['uri'], '-m', model, timeout=60)
    if name not in {q['name'] for q in installed()}:
        return False, f'Could not add it: {out.strip() or "CUPS refused"}'
    if len(installed()) == 1:
        run('lpoptions', '-d', name)
    return True, f'Added {name} ({desc})'


def remove(name):
    run(LPADMIN, '-x', name)


def set_default(name):
    run('lpoptions', '-d', name)            # per user, no admin rights needed


def test_page(name):
    out = run('lp', '-d', name, TESTPAGE)
    return out.strip() or 'Test page sent'
