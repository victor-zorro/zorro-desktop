"""hardware check rows"""
import json
import os
import re
import shutil
from pathlib import Path
from .base import run, spawn, sysread


# ---- hardware check -----------------------------------------------------------------------

FP_VENDORS = {'06cb': 'Synaptics', '27c6': 'Goodix', '138a': 'Validity', '147e': 'UPEK',
              '10a5': 'FPC', '1c7a': 'EgisTec', '2808': 'FocalTech', '04f3:0c': 'Elan'}
SOUNDS = Path('/usr/share/sounds/freedesktop/stereo')


def driver_of(sysdev):
    try:
        return Path(os.path.realpath(Path(sysdev) / 'driver')).name
    except OSError:
        return '?'


def cameras():
    """[(dev, name, driver, is_ir)]: capture nodes only"""
    out = []
    for d in sorted(Path('/sys/class/video4linux').glob('video*')):
        dev = f'/dev/{d.name}'
        fmts = run('v4l2-ctl', '-d', dev, '--list-formats')
        if "'" not in fmts:
            continue                     # metadata node
        ir = 'GREY' in fmts and 'YUYV' not in fmts and 'MJPG' not in fmts
        out.append((dev, sysread(d / 'name').split(':')[0], driver_of(d / 'device'), ir))
    return out


def audio_state(which):
    """(volume %, muted, name) of the default sink / source"""
    out = run('wpctl', 'get-volume', f'@DEFAULT_AUDIO_{which}@')
    m = re.search(r'([\d.]+)', out)
    name = ''
    insp = run('wpctl', 'inspect', f'@DEFAULT_AUDIO_{which}@')
    n = re.search(r'node\.description = "([^"]+)"', insp) or re.search(r'node\.nick = "([^"]+)"', insp)
    if n:
        name = n.group(1)
    return (round(float(m.group(1)) * 100) if m else None), '[MUTED]' in out, name


def bt_state():
    show = run('bluetoothctl', 'show')
    if 'Controller' not in show:
        return None
    powered = 'Powered: yes' in show
    devs = []
    for line in run('bluetoothctl', 'devices', 'Paired').splitlines():
        p = line.split(' ', 2)
        if len(p) == 3 and p[0] == 'Device':
            info = run('bluetoothctl', 'info', p[1])
            devs.append((p[1], p[2], 'Connected: yes' in info))
    return {'powered': powered, 'paired': devs}


def input_names():
    return re.findall(r'N: Name="([^"]+)"', sysread('/proc/bus/input/devices'))


def hardware_rows(ui):
    """the device list; ui supplies the actions. Runs in a thread (some checks are slow)."""
    rows = []
    lsusb = run('lsusb')
    lspci = run('lspci')

    cams = cameras()
    rgb = [c for c in cams if not c[3]]
    ir = [c for c in cams if c[3]]
    if rgb:
        dev, name, drv, _ = rgb[0]
        detail = f'{name} · {dev} · driver {drv}'
        if ir:
            detail += f'\nInfrared camera found too ({ir[0][0]}): usable for face unlock later'
        rows.append(('camera-web-symbolic', 'Webcam', 'ok', detail,
                     [('Preview', lambda d=dev: ui.webcam(d))]))
    else:
        rows.append(('camera-web-symbolic', 'Webcam', 'warn',
                     'No camera found. Check the BIOS (Security → I/O Port Access → Camera).', []))

    vol, muted, name = audio_state('SOURCE')
    if vol is None:
        rows.append(('audio-input-microphone-symbolic', 'Microphone', 'warn', 'No microphone found', []))
    else:
        rows.append(('microphone-disabled-symbolic' if muted else 'audio-input-microphone-symbolic',
                     'Microphone', 'warn' if muted else 'ok',
                     f'{name} · {"MUTED" if muted else f"on, level {vol}%"}',
                     [('Unmute' if muted else 'Mute', ui.mic_toggle),
                      ('Test: record 3 s', ui.mic_test)]))

    vol, muted, name = audio_state('SINK')
    if vol is None:
        rows.append(('audio-speakers-symbolic', 'Speakers', 'warn', 'No sound output found', []))
    else:
        rows.append(('audio-speakers-symbolic', 'Speakers', 'warn' if muted else 'ok',
                     f'{name} · {"MUTED" if muted else f"volume {vol}%"}',
                     [('Test: left / right', ui.speaker_test)]))

    bt = bt_state()
    usb_bt = next((l.split(' ', 6)[-1] for l in lsusb.splitlines() if 'Bluetooth' in l), 'adapter')
    if bt is None:
        rows.append(('bluetooth-symbolic', 'Bluetooth', 'warn',
                     'No Bluetooth controller (switched off with F8 / airplane mode?)', []))
    else:
        detail = f'{usb_bt} · {"on" if bt["powered"] else "off"}'
        if bt['powered']:
            detail += ' · ' + (f'{len(bt["paired"])} paired' if bt['paired'] else 'nothing paired yet')
        acts = [('Turn off' if bt['powered'] else 'Turn on', lambda p=bt['powered']: ui.bt_power(not p))]
        if bt['powered']:
            acts.append(('Scan & pair…', ui.bt_scan))
        rows.append(('bluetooth-active-symbolic' if bt['powered'] else 'bluetooth-disabled-symbolic',
                     'Bluetooth', 'ok' if bt['powered'] else 'off', detail, acts))
        for mac, dname, conn in bt['paired']:
            rows.append((None, f'    {dname}', 'ok' if conn else 'off',
                         f'    {mac} · {"connected" if conn else "not connected"}',
                         [('Disconnect' if conn else 'Connect',
                           lambda m=mac, c=conn: ui.bt_cmd('disconnect' if c else 'connect', m)),
                          ('Forget', lambda m=mac: ui.bt_cmd('remove', m))]))
        for mac, dname in ui.bt_found:
            rows.append((None, f'    {dname}', 'off', f'    {mac} · found nearby',
                         [('Pair & connect', lambda m=mac: ui.bt_pair(m))]))

    wifi = next((l for l in run('nmcli', '-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'dev').splitlines()
                 if ':wifi:' in l), None)
    wcard = next((l.split(': ', 1)[-1] for l in lspci.splitlines() if 'Network controller' in l), '')
    if wifi:
        dev, _, state, conn = wifi.split(':', 3)
        sig = next((l.split(':')[1] for l in run('nmcli', '-t', '-f', 'ACTIVE,SIGNAL', 'dev',
                                                     'wifi').splitlines() if l.startswith('yes:')), '')
        ok = state == 'connected'
        rows.append(('network-wireless-symbolic', 'Wi-Fi', 'ok' if ok else 'off',
                     f'{wcard} · driver {driver_of(f"/sys/class/net/{dev}/device")}\n'
                     + (f'connected to {conn}, signal {sig}%' if ok else state),
                     [('Connections…', lambda: spawn(['nm-connection-editor']))]))
    else:
        rows.append(('network-wireless-offline-symbolic', 'Wi-Fi', 'warn', 'No Wi-Fi adapter', []))

    modem = next((l.split(': ', 1)[-1] for l in lspci.splitlines()
                  if 'modem' in l.lower() or 'Cellular' in l), None)
    if modem:
        from . import pages_mobile as pm
        detail, state = 'Set up in the Mobile tab', 'off'
        if os.path.exists(pm.LTE):
            ok, out = pm.lte('state', timeout=40)
            try:
                st = json.loads(out.strip().splitlines()[-1]) if ok else {}
            except (ValueError, IndexError):
                st = {}
            if st.get('data'):
                detail, state = f'Mobile data on ({st.get("operator", "")} {st.get("tech", "")}, {st.get("ip")})', 'ok'
            elif st.get('registered'):
                detail, state = f'{st.get("operator", "")} {st.get("tech", "")}, signal {st.get("signal")}%: mobile data off', 'ok'
            elif st.get('awake'):
                detail, state = f'Modem on, SIM: {st.get("sim") or "?"}', 'warn'
            else:
                detail = 'Modem asleep: start it in the Mobile tab'
        else:
            detail, state = 'Not installed yet: sudo apps/zorro-thinkpad/install.sh', 'warn'
        rows.append(('network-cellular-symbolic', 'Mobile data (LTE)', state, f'{modem}\n{detail}',
                     [('Mobile tab', lambda: ui.show_page('lte:0'))]))

    # printers have their own page (Hardware → Printers, zsettings/printers.py)

    names = input_names()
    touch = next((n for n in names if 'Touch System' in n or 'Touchscreen' in n), None)
    rows.append(('input-touchpad-symbolic', 'Touchscreen', 'ok' if touch else 'off',
                 touch or 'none', []))
    pads = [n for n in names if 'TouchPad' in n or 'TrackPoint' in n]
    rows.append(('input-mouse-symbolic', 'Touchpad and TrackPoint', 'ok' if pads else 'warn',
                 ' · '.join(pads) or 'not found', []))

    fp = None
    for l in lsusb.splitlines():
        m = re.search(r'ID ([0-9a-f]{4}):([0-9a-f]{4})', l)
        if m and (m.group(1) in FP_VENDORS or f'{m.group(1)}:{m.group(2)[:2]}' in FP_VENDORS):
            fp = l.split(m.group(0), 1)[1].strip() or FP_VENDORS.get(m.group(1))
    if fp:
        have = shutil.which('fprintd-enroll')
        rows.append(('auth-fingerprint-symbolic', 'Fingerprint', 'ok' if have else 'warn',
                     f'{fp}\n' + ('fprintd installed' if have else
                                  'Reader found; needs fprintd (next step: enroll + use for login)'),
                     []))
    else:
        rows.append(('auth-fingerprint-symbolic', 'Fingerprint', 'warn',
                     'No fingerprint reader found. If this ThinkPad has one (in the power button), '
                     'switch it on in the BIOS: Security → I/O Port Access → Fingerprint Reader.',
                     []))
    return rows
