"""First fill, part two: what is planned. Open features and the decisions from
plan/SPEC.md. Each entry names its place and a few words to find; the text of the
item is the SPEC's own sentence, so an entry whose words are gone is left out."""
from . import paths, store
from .fill_md import blocks, first_clause, plain, sentences

APPS_ROW = 'Connect: Transfer'
AI_SERVICE = 'zorro-ai: the one AI service'
# (kind, app, category, title, words to find in SPEC.md)
PLAN = [
    ('feature', 'Desktop', 'App', 'The Desktop app', 'Desktop: use'),
    ('feature', 'Desktop', 'Switcher', 'App switcher in the top bar', 'The switcher in the top bar'),
    ('feature', 'System', 'App', 'The System app', 'System: settings and hardware'),
    ('feature', 'System', 'Monitors', 'Monitors page', 'System: settings and hardware'),
    ('feature', 'Connect', 'App', 'The Connect app', APPS_ROW),
    ('feature', 'Connect', 'Bootstrap', 'Bootstrap: the one-liner', APPS_ROW),
    ('feature', 'Connect', 'Bootstrap', 'Bootstrap: USB installer', APPS_ROW),
    ('feature', 'Connect', 'Bootstrap', 'Bootstrap: ISO image', APPS_ROW),
    ('feature', 'Connect', 'Install apps', 'Install apps page', APPS_ROW),
    ('feature', 'Connect', 'NetBird', 'NetBird link', APPS_ROW),
    ('feature', 'DEVS', 'App', 'The DEVS web page', 'DEVS: catalogue'),
    ('feature', 'DEVS', 'AI', 'AI sorts, writes steps, fixes', 'In DEVS the AI sorts'),
    ('feature', 'Intelligence', 'App', 'The Intelligence app', 'Intelligence: search + AI'),
    ('feature', 'Intelligence', 'zorro-ai', 'zorro-ai: one AI service', AI_SERVICE),
    ('feature', 'Intelligence', 'zorro-ai', 'Service on a unix socket', 'A user service listening'),
    ('feature', 'Intelligence', 'zorro-ai', 'Ask: answers in pieces', 'After done or error'),
    ('feature', 'Intelligence', 'zorro-ai', 'Status, settings, models', 'Other ops'),
    ('feature', 'Intelligence', 'zorro-ai', 'Mistral key file', 'The Mistral key lives'),
    ('feature', 'Intelligence', 'Engines', 'Engines: claude, mistral, local', 'Engines:'),
    ('feature', 'Intelligence', 'Engines', 'Engine per place, or auto', 'The user chooses per place'),
    ('feature', 'Intelligence', 'Engines', 'Local model follows power', 'Local model choice may follow'),
    ('feature', 'Intelligence', 'Privacy', 'Switch: nothing leaves', 'nothing leaves this laptop'),
    ('feature', 'Intelligence', 'Privacy', 'Answers name engine and files', 'The AI reads only folders'),
    ('feature', 'Dialer', 'Parts', 'AI part replaces System', 'Dialer parts:'),
    ('feature', 'Dialer', 'System', 'System tiles move out', 'The System part goes'),
    ('feature', 'Dialer', 'Messages', 'Messages and SMS, one list', 'Messages = notifications'),
    ('feature', 'Dialer', 'AI', 'AI part: the chat', "AI = Intelligence's chat"),
    ('feature', 'Music', 'Output', 'Fast output picker', 'Music gets the fast output picker'),
    ('feature', 'Transfer', 'Devices', 'New device joins DEVS', 'each device set up by Transfer'),
    ('decision', 'Desktop', 'Apps', 'Switcher: four apps', 'The switcher in the top bar'),
    ('decision', 'Intelligence', 'Apps', 'Intelligence stands apart', 'Intelligence: search + AI'),
    ('decision', 'Intelligence', 'zorro-ai', 'One request per connection', 'One request per connection'),
    ('decision', 'Intelligence', 'zorro-ai', 'Callers choose the context', 'zorro-ai never reads files itself'),
    ('decision', 'Intelligence', 'zorro-ai', 'Closing cancels the answer', 'Closing the connection'),
    ('decision', 'Dialer', 'Parts', 'Six parts, AI not System', 'Dialer parts:'),
    ('decision', 'Dialer', 'Messages', 'Messages: one list', 'Messages = notifications'),
    ('decision', 'DEVS', 'Apps', 'DEVS is a web page', 'DEVS: catalogue'),
    ('decision', 'DEVS', 'Data', 'Items are files', 'Items are files'),
    ('decision', 'DEVS', 'Data', 'Never in the public repo', 'Never in the public repo'),
    ('decision', 'DEVS', 'Data', 'Kinds of items', 'kind: feature'),
    ('decision', 'DEVS', 'Data', 'Three statuses', 'status: open'),
    ('decision', 'DEVS', 'Tests', 'Stale after an app change', 'a test made on an older'),
    ('decision', 'DEVS', 'Tests', 'Devices add themselves', 'Devices: this one'),
]
# Sections whose every bullet is a decision: heading -> (app, category)
DECIDED = {'AI decisions': ('Intelligence', 'AI'),
           'How every part is built and tested': ('DEVS', 'Build')}


def spec_parts(text):
    """(section, sentence) for every sentence, bullet and table row of the SPEC."""
    out, section = [], ''
    for kind, value in blocks(text):
        if kind in ('h1', 'heading'):
            section = value
        elif kind == 'bullet':
            out.append((section, value))
        elif kind == 'para':
            out += [(section, s) for s in sentences(value)]
        elif kind == 'row' and len(value) > 1:
            cells = [plain(c) for c in value]
            where = f' Where: {cells[2]}.' if len(cells) > 2 else ''
            out.append((section, f'{cells[0]}: {cells[1]}.{where}'))
    return out


def planned(parts):
    out = []
    for kind, app, category, title, words in PLAN:
        text = next((plain(s) for _, s in parts if words in plain(s)), None)
        if text:
            status = 'done' if kind == 'decision' else 'open'
            fields = {'app': app, 'category': category, 'text': text[:1500], 'status': status}
            out.append(store.new_item(kind, title, fields))
    return out


def decided(parts):
    out = []
    for section, sentence in parts:
        if section in DECIDED and not sentence.endswith(':'):
            app, category = DECIDED[section]
            fields = {'app': app, 'category': category, 'text': plain(sentence)[:1500], 'status': 'done'}
            out.append(store.new_item('decision', first_clause(sentence), fields))
    return out


def items():
    try:
        text = (paths.repo() / 'plan' / 'SPEC.md').read_text()
    except OSError:
        return []
    parts = spec_parts(text)
    return planned(parts) + decided(parts)
