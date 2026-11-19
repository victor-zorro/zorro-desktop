#!/usr/bin/env bash
# Install Sweep notes for the current user (no sudo). Safe to rerun.
# Needs: python3-gi, python3-gi-cairo, gir1.2-gtk-3.0; python3-numpy and the zorro-search
# index for the "best match" (works without, just no suggestion).
set -euo pipefail
here=$(dirname "$(realpath "$0")")
mkdir -p ~/.local/bin ~/.local/share/applications
ln -sfn "$here/zorro-sweep" ~/.local/bin/zorro-sweep
ln -sfn "$here/zorro-sweep.desktop" ~/.local/share/applications/zorro-sweep.desktop

# the Obsidian plugin, in every vault (Obsidian Sync takes it to the phone): copied, not linked,
# so Sync sees real files. Enabled in community-plugins.json; the vault list is for its picker.
# Set ZORRO_OBSIDIAN_JSON to use another vault list (tests).
python3 - "$here/obsidian-plugin" "${ZORRO_OBSIDIAN_JSON:-$HOME/.config/obsidian/obsidian.json}" <<'PY'
import json, os, re, shutil, sys
from pathlib import Path
src, reg = Path(sys.argv[1]), Path(sys.argv[2])
try:
    vaults = [Path(v['path']) for v in json.loads(reg.read_text()).get('vaults', {}).values()]
except (OSError, ValueError):
    vaults = []
vaults = sorted(v for v in vaults if (v / '.obsidian').is_dir())
names = [v.name for v in vaults]
for v in vaults:
    dst = v / '.obsidian/plugins/zorro-sweep'
    dst.mkdir(parents=True, exist_ok=True)
    for f in ('main.js', 'manifest.json', 'styles.css'):
        if not (dst / f).exists() or (dst / f).read_bytes() != (src / f).read_bytes():
            shutil.copyfile(src / f, dst / f)
    cp = v / '.obsidian/community-plugins.json'
    try:
        on = json.loads(cp.read_text())
    except (OSError, ValueError):
        on = []
    if 'zorro-sweep' not in on:
        cp.write_text(json.dumps(on + ['zorro-sweep'], indent=2))
    data = dst / 'data.json'
    try:
        d = json.loads(data.read_text())
    except (OSError, ValueError):
        d = {}
    old = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'zorro-sweep' / (
        re.sub(r'[^\w.-]+', '_', v.name) + '.json')
    if 'kept' not in d and old.exists():   # the laptop app's progress so far: shared from now on
        try:
            d.update(json.loads(old.read_text()))
        except (OSError, ValueError):
            pass
        d['vaults'] = None
    if d.get('vaults') != names:
        d['vaults'] = names
        tmp = data.with_name('data.json.tmp')
        tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False))
        os.replace(tmp, data)
print(f"Sweep notes plugin in {len(vaults)} vault(s): {', '.join(names)}")
PY
echo "Sweep notes installed (Dialer / rofi: Sweep notes; in Obsidian: the brush button)"
