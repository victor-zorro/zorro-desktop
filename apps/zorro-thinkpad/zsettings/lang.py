"""Spell-check languages, all checked at the same time: a word is right when it is right in
any of them, so Dutch and English (and more) mixed in one sentence get no red lines, while
a real typo still does. Set for Firefox (every profile, also the web apps) and Obsidian.

  python3 -m zsettings.lang apply     set the chosen languages again (e.g. on a new machine)

Choice: ~/.config/zorro-desktop/languages.json {"spell": ["en-GB", "nl"]}
Dictionaries: Debian's hunspell packages, added / removed by zorro-lang-helper (pkexec).
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
CONF = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config')) / 'zorro-desktop' / 'languages.json'
HUNSPELL = Path('/usr/share/hunspell')
HELPER = '/usr/local/libexec/zorro-lang-helper'
OBSIDIAN_PREFS = HOME / '.config/obsidian/Preferences'
# code: (name, hunspell file prefix, Obsidian / Chromium code)
LANGS = {
    'en-GB': ('English (UK)', 'en_GB', 'en-GB'),
    'en-US': ('English (US)', 'en_US', 'en-US'),
    'nl': ('Dutch', 'nl', 'nl'),
    'de': ('German', 'de_DE', 'de-DE'),
    'fr': ('French', 'fr_FR', 'fr-FR'),
    'es': ('Spanish', 'es_ES', 'es-ES'),
    'it': ('Italian', 'it_IT', 'it-IT'),
    'pt': ('Portuguese', 'pt_PT', 'pt-PT'),
}
DEFAULT = ['en-GB', 'nl']
BEGIN, END = '// zorro: spell-check languages (Zorro app → Languages)', '// zorro: end'


def chosen():
    try:
        v = json.loads(CONF.read_text()).get('spell', DEFAULT)
        return [x for x in v if x in LANGS] or DEFAULT
    except (OSError, ValueError):
        return list(DEFAULT)


def choose(langs):
    CONF.parent.mkdir(parents=True, exist_ok=True)
    CONF.write_text(json.dumps({'spell': [x for x in LANGS if x in langs]}, indent=1))


def installed(code):
    """the hunspell dictionary file name for a language, or None when it is not installed"""
    pre = LANGS[code][1]
    names = sorted(p.stem for p in HUNSPELL.glob('*.dic')) if HUNSPELL.is_dir() else []
    if pre in names:                    # exact: nl, de_DE, en_GB
        return pre
    if code.startswith('en-'):          # English: only the variant asked for
        return None
    lang = pre.split('_')[0]            # else any region of the language (es_MX, fr_BE…)
    return next((n for n in names if n.split('_')[0] == lang), None)


def firefox_profiles():
    out = []
    for base in (HOME / '.config/mozilla/firefox', HOME / '.mozilla/firefox'):
        out += [p for p in base.glob('*') if (p / 'prefs.js').exists()]
    out += [p for p in (HOME / '.local/share').glob('firefox-*') if (p / 'prefs.js').exists()]
    return out


def set_firefox(dicts):
    """a managed block in every profile's user.js (Firefox reads it when it starts)"""
    block = [BEGIN, f'user_pref("spellchecker.dictionary_path", "{HUNSPELL}");',
             f'user_pref("spellchecker.dictionary", "{",".join(d.replace("_", "-") for d in dicts)}");',
             'user_pref("layout.spellcheckDefault", 1);', END]
    n = 0
    for prof in firefox_profiles():
        f = prof / 'user.js'
        try:
            old = f.read_text()
        except OSError:
            old = ''
        old = re.sub(re.escape(BEGIN) + r'.*?' + re.escape(END) + r'\n?', '', old, flags=re.S)
        f.write_text(old.rstrip('\n') + ('\n' if old.strip() else '') + '\n'.join(block) + '\n')
        n += 1
    return n


def obsidian_open():
    return subprocess.run(['pgrep', '-r', 'R,S,D', '-x', 'obsidian'], capture_output=True).returncode == 0


def set_obsidian(codes):
    """Obsidian's spell-check languages (it fetches the dictionaries itself); only while it is
    closed, because it writes this file when it quits"""
    if not OBSIDIAN_PREFS.exists():
        return 'not used'
    if obsidian_open():
        return 'open'
    p = json.loads(OBSIDIAN_PREFS.read_text())
    p.setdefault('spellcheck', {})['dictionaries'] = [LANGS[c][2] for c in codes]
    p['spellcheck']['dictionary'] = ''
    tmp = OBSIDIAN_PREFS.with_suffix('.zorro-tmp')
    tmp.write_text(json.dumps(p, separators=(',', ':')))
    os.replace(tmp, OBSIDIAN_PREFS)
    return 'set'


def apply(codes=None):
    """set Firefox and Obsidian to the chosen languages; returns a line of what happened"""
    codes = codes or chosen()
    have = [installed(c) for c in codes]
    dicts = [d for d in have if d]
    missing = [LANGS[c][0] for c, d in zip(codes, have) if not d]
    n = set_firefox(dicts)
    ob = set_obsidian(codes)
    msg = [f'Firefox: {n} profiles set (restart Firefox)' if n else 'Firefox: no profile found']
    msg.append({'set': 'Obsidian: set', 'open': 'Obsidian is open: close it and press Apply again',
                'not used': 'Obsidian: not set up'}[ob])
    if missing:
        msg.append('no dictionary yet for ' + ', '.join(missing))
    return '\n'.join(msg)


if __name__ == '__main__':
    if sys.argv[1:] == ['apply']:
        print(apply())
    else:
        print(__doc__.strip())
