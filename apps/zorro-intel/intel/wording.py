"""Plain words for what zorro-ai reports: engine names, why an engine is not ready, model lines."""
import re

ENGINES = {'claude': 'Claude', 'mistral': 'Mistral cloud', 'local': 'On this laptop'}
CHOICES = {'auto': 'Automatic', **ENGINES}
PLACES = {'dialer': 'Dialer', 'intel': 'Intelligence', 'devs': 'DEVS'}

CLAUDE_MODELS = {'haiku': 'Haiku (fast, light)', 'sonnet': 'Sonnet (balanced)',
                 'opus': 'Opus (most capable)', 'default': 'Program default'}
SUGGESTED_CLAUDE = {'dialer': 'haiku', 'intel': 'sonnet', 'devs': 'sonnet'}   # used when the service sends none

REASONS = (('not installed', 'the claude program is not installed'),
           ('no key', 'no key yet: see Mistral key'),
           ('llama-server', 'the local engine is not installed: see Local models'),
           ('has no', 'no model downloaded yet: see Local models'),
           ('not reachable', 'not reachable now (offline?)'))


def choice(value):
    """the combo entry for a place's setting (local:<model> shows as On this laptop)"""
    if isinstance(value, str) and value.startswith('local:'):
        return 'local'
    return value if value in CHOICES else 'auto'


def claude_options(place, suggested=None):
    """{id: label} for the Claude model combo of one place; the suggested one says so"""
    suggested = (suggested or SUGGESTED_CLAUDE).get(place)
    return {key: f'{label} (suggested)' if key == suggested else label for key, label in CLAUDE_MODELS.items()}


def claude_choice(settings, place, suggested=None):
    """the Claude model id to show for a place: the setting, else the suggestion"""
    value = ((settings or {}).get('claude_models') or {}).get(place)
    return value if value in CLAUDE_MODELS else (suggested or SUGGESTED_CLAUDE).get(place, 'default')


def claude_change(place, value):
    """the settings request for one place's Claude model"""
    return {'claude_models': {place: value}}


def why(text):
    for needle, plain in REASONS:
        if needle in (text or ''):
            return plain
    return (text or 'not ready').split(' (run:')[0]


def plain_error(text):
    """an engine's error without the command-line advice in it"""
    return re.sub(r' \(run: [^)]*\)', '', text or '').strip()


def engine_state(name, state, local_only=False):
    """(mark, line) for one engine of the status reply: ('on', 'Claude: ready')"""
    title = ENGINES.get(name, name)
    if local_only and name != 'local':
        return 'off', f'{title}: off, nothing leaves this laptop'
    if state.get('ready'):
        model = f' ({state["model"]})' if state.get('model') and name == 'local' else ''
        return 'on', f'{title}: ready{model}'
    return 'off', f'{title}: {why(state.get("why"))}'


def local_engine_missing(status):
    """True when llama.cpp itself is not there yet"""
    local = (status.get('engines') or {}).get('local') or {}
    return not local.get('ready') and 'llama-server' in (local.get('why') or '')


def answered_by(message):
    """the dim line under an answer: who answered, and whether it was stopped"""
    parts = [ENGINES.get(message.get('engine'), message.get('engine') or 'No engine')]
    if message.get('model'):
        parts.append(str(message['model']))
    if message.get('partial'):
        parts.append('stopped early')
    if not message.get('sent'):
        parts.append('no files sent')
    return ' · '.join(parts)


def model_line(model):
    """the dim line of one local model"""
    parts = [f'{model.get("size", 0):.1f} GB']
    if model.get('speed') and model['speed'] != 'not measured yet':
        parts.append(model['speed'])
    return ' · '.join(parts) + ' · ' + str(model.get('good_for', ''))


def installed(models):
    """{id: name} of the downloaded models"""
    return {m['id']: m['name'] for m in models if m.get('installed')}


def score_fraction(score, low=0.75, high=0.95):
    """a search score as 0..1 for the small bar"""
    try:
        return max(0.0, min(1.0, (float(score) - low) / (high - low)))
    except (TypeError, ValueError):
        return 0.0
