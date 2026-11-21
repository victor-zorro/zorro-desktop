"""app: Audio tab: outputs, inputs, what plays where, several outputs together (audio.py)"""
import threading
import time

from . import audio
from .base import load_conf
from .ui import Pages, device_list, device_row, heading, idle, in_bg, later, note
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk  # noqa: E402

KIND_ICON = {'Bluetooth': 'bluetooth-symbolic', 'USB': 'media-removable-symbolic',
             'built in': 'audio-speakers-symbolic', 'virtual': 'view-dual-symbolic'}


class AudioPages:
    """Audio tab (a mixin of the app window)"""

    def audio_pages(self):
        outp, inp, play, tog = Pages(), Pages(), Pages(), Pages()
        labels = [note() for _ in range(4)]
        for pages, lb in zip((outp, inp, play, tog), labels):
            pages.footer(lb)
        self.au_labels = labels
        self.au_seen = None

        outp.add(heading('Sound output', 'Output'))
        self.au_out = device_list()
        outp.add(self.au_out)
        t = Gtk.Button(label='Test: left / right', halign=Gtk.Align.START, margin_top=8)
        t.connect('clicked', lambda b: self.speaker_test())
        outp.add(t)
        outp.add(note('Use: the output for everything (also when that device comes back later). '
                      'One app somewhere else: Playing now.'))

        inp.add(heading('Sound input', 'Input'))
        self.au_in = device_list()
        inp.add(self.au_in)
        t = Gtk.Button(label='Test: record 3 s', halign=Gtk.Align.START, margin_top=8)
        t.connect('clicked', lambda b: self.mic_test())
        inp.add(t)
        inp.add(note('A Bluetooth headset used as microphone drops to phone quality while the '
                     'microphone is on; music on another device stays as it is.'))

        play.add(heading('Playing now', 'Playing now'))
        self.au_play = device_list()
        play.add(self.au_play)
        play.add(note('Each app can play on its own output: music on the DAC, a call on the '
                      'earbuds. The choice lasts while the app plays.'))

        tog.add(heading('Several outputs together', 'Together'))
        self.au_tog = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        tog.add(self.au_tog)
        row = Gtk.Box(spacing=8, margin_top=8)
        b = Gtk.Button(label='Play on these together')
        b.get_style_context().add_class('suggested-action')
        b.connect('clicked', lambda b: self.au_together(True))
        row.add(b)
        b = Gtk.Button(label='Stop')
        b.connect('clicked', lambda b: self.au_together(False))
        row.add(b)
        tog.add(row)
        tog.add(note('Makes one extra output, "Together", that plays on all ticked devices; '
                     'use it for everything (Output) or for one app (Playing now). Bluetooth runs '
                     'about 0.2 s behind wired speakers: in the same room that sounds like an '
                     'echo, so mix Bluetooth with Bluetooth, or devices in different rooms.'))

        idle(self.au_refresh)
        self.timers.append(GLib.timeout_add_seconds(3, self.au_tick))
        return outp, inp, play, tog

    def au_say(self, text):
        for lb in self.au_labels:
            lb.set_text(text)

    def au_tick(self):
        if self.tab_on('audio'):
            self.au_refresh()
        return True

    # the sound tests (Audio → Output / Input); they report here
    def mic_test(self):
        def fn():
            import os
            import subprocess
            import tempfile
            from .base import RUNTIME, run
            fd, wav = tempfile.mkstemp(suffix='.wav', prefix='zorro-mic-', dir=RUNTIME)
            os.close(fd)
            idle(lambda: self.au_say('● Recording 3 seconds: say something…') and False)
            p = subprocess.Popen(['pw-record', wav], stderr=subprocess.DEVNULL)
            time.sleep(3)
            p.terminate()
            p.wait()
            idle(lambda: self.au_say('▶ Playing it back…') and False)
            run('pw-play', wav, timeout=8)
            try:
                os.unlink(wav)
            except OSError:
                pass
            return 'Microphone test done: did you hear yourself?'
        self.au_bg('…', fn)

    def speaker_test(self):
        def fn():
            from .base import run
            from .hardware import SOUNDS
            for side in ('left', 'right'):
                run('pw-play', str(SOUNDS / f'audio-channel-front-{side}.oga'))
            return 'You should have heard "front left" from the left and "front right" from the right.'
        self.au_bg('▶ Playing a voice on the left, then on the right…', fn)

    def au_use(self, kind, name):
        """make this the output / input; the equaliser, when on, moves along"""
        from . import eq
        if kind == 'sinks' and eq.settings()['on'] and eq.running():
            eq.retarget(name)
        else:
            audio.use(kind, name)

    def au_bg(self, busy, fn):
        if busy:
            self.au_say(busy)

        def work():
            try:
                msg = fn()
            except Exception as e:      # noqa: BLE001  shown; the page must not stay on "…"
                msg = f'Failed: {e}'
            idle(lambda: (self.au_say(msg or ''), self.au_refresh(force=True)) and False)
        threading.Thread(target=work, daemon=True).start()

    def au_refresh(self, force=False):
        def work():
            data = (audio.devices('sinks'), audio.devices('sources'), audio.streams())
            idle(lambda: self.au_show(*data, force=force) and False)
        threading.Thread(target=work, daemon=True).start()
        return False

    def au_show(self, sinks, sources, streams, force=False):
        # rebuild only when something changed, so a slider being dragged is left alone
        sig = (tuple((d['name'], d['default'], d['muted']) for d in sinks),
               tuple((d['name'], d['default'], d['muted']) for d in sources),
               tuple((s['id'], s['sink']) for s in streams))
        self.vol_sync('sinks', sinks)
        self.vol_sync('sources', sources)
        old = self.au_seen if isinstance(self.au_seen, tuple) and not force else (None, None, None)
        self.au_seen = sig
        if sig[0] != old[0]:
            self.au_devices(self.au_out, 'sinks', sinks)
        if sig[1] != old[1]:
            self.au_devices(self.au_in, 'sources', sources)
        if (sig[2], sig[0]) != (old[2], old[0]):
            self.au_streams(sinks, streams)
        if tuple(n for n, _, _ in sig[0]) != tuple(n for n, _, _ in old[0] or ()):
            self.au_together_list(sinks)
        return True

    def au_devices(self, box, kind, devs):
        for c in box.get_children():
            c.destroy()
        members = load_conf().get('audio', {}).get('together', [])
        names = {d['name']: d['desc'] for d in devs}
        for d in devs:
            what = ' + '.join(names.get(n, n.split('.')[0]) for n in members) if d['together'] else d['kind']
            vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 150, 1)
            vol.set_value(d['volume'])
            vol.set_size_request(220, -1)
            vol.add_mark(100, Gtk.PositionType.BOTTOM, None)
            vol.connect('format-value', lambda w, v: f'{v:.0f}%')
            vol.connect('value-changed', lambda w, n=d['name']: self.au_volume(kind, n, w.get_value()))
            self.vol_follow(vol, kind, d['name'])
            mute = Gtk.ToggleButton(label='Muted' if d['muted'] else 'Mute', active=d['muted'])
            mute.connect('toggled', lambda w, n=d['name']: (
                w.set_label('Muted' if w.get_active() else 'Mute'),
                in_bg(audio.set_mute, kind, n, w.get_active())))
            acts = [mute]
            if not d['default']:
                acts.append(('Use', lambda n=d['name'], t=d['desc']: self.au_bg(
                    f'Switching to {t}…', lambda: (self.au_use(kind, n), f'Now: {t}')[1])))
            box.add(device_row(d['desc'], what + (' · in use' if d['default'] else ''), acts,
                               icon=KIND_ICON.get(d['kind'], 'audio-card-symbolic'),
                               state='on' if d['default'] else 'off', below=[vol]))
        if not devs:
            box.add(note('None found'))
        box.show_all()

    def vol_follow(self, scale, kind, name):
        """keep this slider in step with the real volume (F2 / F3 change it outside the app)"""
        sliders = self.__dict__.setdefault('vol_sliders', {})
        sliders.setdefault((kind, name), []).append(scale)
        scale.connect('destroy', lambda w: sliders.get((kind, name), []).remove(w)
                      if w in sliders.get((kind, name), []) else None)

    def vol_sync(self, kind, devs):
        """move the sliders to the volume read now; not one the user is moving"""
        touched = self.__dict__.setdefault('vol_touched', {})
        self.vol_setting = True
        try:
            for d in devs:
                if time.monotonic() - touched.get((kind, d['name']), 0) < 2:
                    continue
                for s in self.__dict__.get('vol_sliders', {}).get((kind, d['name']), []):
                    if abs(s.get_value() - d['volume']) >= 1:
                        s.set_value(d['volume'])
        finally:
            self.vol_setting = False

    def au_volume(self, kind, name, value):
        """apply after the slider rests a moment (no pactl per pixel)"""
        if getattr(self, 'vol_setting', False):
            return                      # moved by vol_sync, not by the user
        key = (kind, name)
        self.__dict__.setdefault('vol_touched', {})[key] = time.monotonic()
        later(f'volume-{kind}-{name}', lambda: in_bg(audio.set_volume, kind, name, value, finish=True), 120)

    def au_streams(self, sinks, streams):
        for c in self.au_play.get_children():
            c.destroy()
        for s in streams:
            combo = Gtk.ComboBoxText()
            for d in sinks:
                combo.append(d['name'], d['desc'])
            combo.set_active_id(s['sink'])
            combo.connect('changed', lambda w, i=s['id'], a=s['app']: self.au_move(
                i, a, w.get_active_id(), w.get_active_text()))
            what = s['what'][:80] if s['what'] and s['what'] != '(null)' else ''
            self.au_play.add(device_row(s['app'], what, [combo]))
        if not streams:
            self.au_play.add(note('Nothing is playing right now.'))
        self.au_play.show_all()

    def au_move(self, stream, app, sink, sink_text):
        self.au_bg(f'Moving {app}…', lambda: (audio.move(stream, sink), f'{app} → {sink_text}')[1])

    def au_together_list(self, sinks):
        for c in self.au_tog.get_children():
            c.destroy()
        members = set(load_conf().get('audio', {}).get('together', []))
        self.au_checks = []
        for d in sinks:
            if d['together']:
                continue
            cb = Gtk.CheckButton(label=f'{d["desc"]}  ({d["kind"]})', active=d['name'] in members)
            cb.zname, cb.zdesc = d['name'], d['desc']
            self.au_checks.append(cb)
            self.au_tog.add(cb)
        self.au_tog.show_all()

    def au_together(self, on):
        picked = [(c.zname, c.zdesc) for c in self.au_checks if c.get_active()] if on else []
        if on and len(picked) < 2:
            self.au_say('Tick at least two outputs')
            return
        self.au_bg('Setting up…' if on else 'Stopping…',
                   lambda: audio.together_set([n for n, _ in picked]))
