"""Finding senders: a broadcast on the local network, and a knock on every connected
NetBird peer."""
import json
import socket
import subprocess
import threading
import time

from . import net, state


def netbird_peers():
    """[(address, name)] of the connected NetBird peers"""
    try:
        st = json.loads(subprocess.run(['netbird', 'status', '--json'], capture_output=True,
                                       text=True, timeout=4).stdout or '{}')
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    out = []
    for p in (st.get('peers') or {}).get('details') or []:
        if p.get('status') == 'Connected':
            ip = (p.get('netbirdIp') or '').split('/')[0]
            if ip:
                out.append((ip, (p.get('fqdn') or ip).split('.')[0]))
    return out


def probe(host, name, found):
    """is a sender listening on this host? Then it goes into found"""
    try:
        s = net.connect(host, timeout=2)
        try:
            net.send_json(s, {'op': 'probe'})
            r = net.recv_json(s)
        finally:
            s.close()
        if r.get('magic') == net.MAGIC.decode():
            found[host] = {'name': str(r.get('name') or name), 'host': host, 'via': 'netbird'}
    except (OSError, ValueError):
        pass


def listen(u, end, found):
    """collect the answers to the broadcast until the time is up"""
    while time.time() < end:
        try:
            data, addr = u.recvfrom(512)
            r = json.loads(data)
            name = str(r.get('name') or addr[0]) if isinstance(r, dict) else addr[0]
            found.setdefault(addr[0], {'name': name, 'host': addr[0],
                                       'via': state.route_kind(addr[0]) or 'local network'})
        except (OSError, ValueError):
            pass


def discover(wait=1.5):
    """senders on the local network and among the NetBird peers: [{name, host, via}]"""
    found = {}
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    u.settimeout(0.3)
    try:
        u.sendto(net.MAGIC + b' who?', ('255.255.255.255', net.DISCOVER_PORT))
    except OSError:
        pass
    probes = [threading.Thread(target=probe, args=(host, name, found), daemon=True)
              for host, name in netbird_peers()]
    for th in probes:
        th.start()
    end = time.time() + wait
    listen(u, end, found)
    u.close()
    for th in probes:
        th.join(max(0, end - time.time()) + 1)
    mine = state.device_name()
    return [f for f in found.values() if f['name'] != mine or f['host'] in ('127.0.0.1', '::1')]
