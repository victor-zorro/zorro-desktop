"""Finding Zorro devices nearby: a broadcast on the local network and a probe of every
connected NetBird peer, both answered by the other device's beacon (beacon.py). Each name
and address once, by its best way: a cable before Wi-Fi, the local network before NetBird;
never this device itself. Two devices with the same name are both listed (with their
addresses): another device cannot take the place of yours by using its name."""
import json
import socket
import subprocess
import threading
import time

from . import net, state

MAX_PEERS = 64                  # NetBird peers probed at most
BROADCASTS = None               # tests: the addresses to ask instead of the network's
BEST = ('cable', 'local network', 'local', 'wifi', 'mobile', 'netbird')


def netbird_peers():
    """the addresses of the connected NetBird peers"""
    try:
        st = json.loads(subprocess.run(['netbird', 'status', '--json'], capture_output=True,
                                       text=True, timeout=4).stdout or '{}')
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    out = []
    for p in (st.get('peers') or {}).get('details') or []:
        ip = (p.get('netbirdIp') or '').split('/')[0] if isinstance(p, dict) else ''
        if ip and p.get('status') == 'Connected':
            out.append(ip)
    return out[:MAX_PEERS]


def broadcasts():
    """where "who?" goes: everyone on this network, and each network card's own broadcast
    address (a cable straight between two devices has no default route)"""
    if BROADCASTS is not None:
        return BROADCASTS
    out = ['255.255.255.255']
    try:
        links = json.loads(subprocess.run(['ip', '-j', '-4', 'addr', 'show', 'up'],
                                          capture_output=True, text=True, timeout=3).stdout or '[]')
    except (OSError, ValueError, subprocess.SubprocessError):
        links = []
    for link in links:
        if not link.get('ifname', '').startswith(('lo', 'wt')):
            out += [a['broadcast'] for a in link.get('addr_info', []) if a.get('broadcast')]
    return list(dict.fromkeys(out))


def valid(r, sending=None):
    """{name, sending} from a beacon's answer, None when it is not one"""
    if not isinstance(r, dict) or r.get('magic') != net.MAGIC.decode():
        return None
    name = r.get('name')
    if not isinstance(name, str) or not name.strip():
        return None
    return {'name': name.strip()[:64], 'sending': r.get('sending', sending) is True}


def ask(host, port, msg, timeout=2):
    """one request to a beacon (or a sender): its answer, None when there is none"""
    try:
        s = net.connect(host, port, timeout=timeout)
        try:
            net.send_json(s, msg)
            r = json.loads(net.recv_frame(s, limit=1024))
        finally:
            s.close()
    except (OSError, ValueError):
        return None
    return r if isinstance(r, dict) else None


def probe(host, found):
    """a NetBird peer: its beacon, or else a sender on the transfer port (an older device)"""
    f = valid(ask(host, net.BEACON_PORT, {'op': 'probe'})) or \
        valid(ask(host, net.PORT, {'op': 'probe'}), sending=True)
    if f:
        found[host] = dict(f, host=host, via='netbird')


def listen(u, end, found):
    """collect the answers to the broadcast until the time is up"""
    while time.time() < end:
        try:
            data, addr = u.recvfrom(1024)
            f = valid(json.loads(data))
        except (OSError, ValueError):
            continue
        if f and addr[0] not in found:
            found[addr[0]] = dict(f, host=addr[0],
                                  via=state.route_kind(addr[0]) or 'local network')


def best(devices):
    """each name and address once, by its best way; not this device"""
    mine = state.device_name()
    out = {}
    for f in sorted(devices, key=lambda f: BEST.index(f['via']) if f['via'] in BEST else 2):
        if f['name'] == mine and f['via'] == 'local':
            continue                    # this device's own beacon
        out.setdefault((f['name'], f['host']), f)
    return sorted(out.values(), key=lambda f: (f['name'].lower(), f['host']))


def discover(wait=1.5):
    """Zorro devices nearby: [{name, host, via, sending}]"""
    lan, peers = {}, {}
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    u.settimeout(0.3)
    for addr in broadcasts():
        try:
            u.sendto(net.WHO, (addr, net.DISCOVER_PORT))
        except OSError:
            pass
    probes = [threading.Thread(target=probe, args=(host, peers), daemon=True)
              for host in netbird_peers()]
    for th in probes:
        th.start()
    end = time.time() + wait
    try:
        listen(u, end, lan)
    finally:
        u.close()
    for th in probes:
        th.join(max(0, end - time.time()) + 4)
    return best(list(lan.values()) + list(peers.values()))


def knock(host):
    """ask the device at host to send its setup: it shows a notification there"""
    return ask(host, net.BEACON_PORT, {'op': 'knock', 'name': state.device_name()}) or {}
