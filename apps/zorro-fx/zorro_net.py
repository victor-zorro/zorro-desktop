"""Who may talk to the small servers on this device (DEVS, the plan page, Transfer's beacon
and sender): this device itself, NetBird, and the home network. Standard library only.

  import sys; sys.path.insert(0, '<repo>/apps/zorro-fx')
  import zorro_net

"Home" is known by its router: the first network these servers see becomes home (its
router's hardware address is kept in ~/.config/zorro/home.json); on any other network,
a café's Wi-Fi or the mobile network, other devices are not answered. Add or remove
routers in that file, or with `python3 zorro_net.py home|forget`.
"""
import ipaddress
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

KEEP = 20.0                     # seconds the picture of the network is reused
LAN = ('en', 'eth', 'wl', 'br')
_seen = {'at': 0.0, 'nets': [], 'home': False}


def home_file():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'zorro' / 'home.json'


def ip_json(*args):
    try:
        out = subprocess.run(['ip', '-j', *args], capture_output=True, text=True, timeout=5).stdout
        return json.loads(out or '[]')
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def networks():
    """[(interface, network)] this device is connected to"""
    found = []
    for dev in ip_json('addr'):
        for a in dev.get('addr_info', []):
            try:
                net = ipaddress.ip_network(f"{a['local']}/{a['prefixlen']}", strict=False)
            except (KeyError, ValueError):
                continue
            found.append((dev.get('ifname', ''), net))
    return found


def routers():
    """hardware addresses of the routers this device goes out through"""
    hops = {(r.get('gateway'), r.get('dev')) for r in ip_json('route', 'show', 'default') if r.get('gateway')}
    macs = set()
    for n in ip_json('neigh'):
        if (n.get('dst'), n.get('dev')) in hops and n.get('lladdr'):
            macs.add(n['lladdr'].lower())
    return macs


def home_routers():
    try:
        saved = json.loads(home_file().read_text()).get('routers', [])
        return {str(m).lower() for m in saved}
    except FileNotFoundError:
        return None
    except (OSError, ValueError, AttributeError):
        return set()


def remember_home(macs):
    path = home_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps({'routers': sorted(macs)}, indent=1) + '\n')
    tmp.replace(path)


def look():
    """the networks, and whether this is home (the first network ever seen becomes home)"""
    now = time.monotonic()
    if now - _seen['at'] < KEEP:
        return _seen
    here, home = routers(), home_routers()
    if home is None and here:
        remember_home(here)
        home = here
    _seen.update(at=now, nets=networks(), home=bool(here & (home or set())))
    return _seen


def trusted(addr):
    """may this address use the servers? itself, NetBird, or the home network"""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    ip = getattr(ip, 'ipv4_mapped', None) or ip
    if ip.is_loopback:
        return True
    seen = look()
    for ifname, net in seen['nets']:
        if ip.version == net.version and ip in net and not ip.is_link_local:
            if ifname.startswith('wt'):
                return True
            if ifname.startswith(LAN):
                return seen['home']
    return False


def own_names():
    """the names and addresses this device answers to (for a web server's Host check)"""
    names = {'localhost', '127.0.0.1', '::1', socket.gethostname().lower()}
    names |= {str(a['local']) for dev in ip_json('addr') for a in dev.get('addr_info', []) if a.get('local')}
    return names


def host_ok(host_header):
    """the Host a browser asked for is this device (stops a website posing as it)"""
    host = (host_header or '').strip().lower()
    host = host[1:].split(']')[0] if host.startswith('[') else host.rsplit(':', 1)[0] if ':' in host else host
    return host in own_names() or host.removesuffix('.local') in own_names()


def same_site(headers):
    """a browser request that did not come from another website's page"""
    origin = headers.get('Origin')
    if not origin or origin == 'null':
        return origin is None
    return origin.split('://', 1)[-1].lower() == (headers.get('Host') or '').lower()


if __name__ == '__main__':
    if sys.argv[1:] == ['home']:
        remember_home((home_routers() or set()) | routers())
    elif sys.argv[1:] == ['forget']:
        remember_home(set())
    print('routers here:', sorted(routers()), '· home:', sorted(home_routers() or []), '· at home:', look()['home'])
