"""What the service does with one request. send(obj) writes one reply line."""
import time

from . import config, models, router
from .engines import EngineError, in_turns, without_local_answers

PLACES = config.PLACES


def handle(request, send, stop_event, engines):
    op = request.get('op') if isinstance(request, dict) else None
    if op == 'ask':
        ask(request, send, stop_event, engines)
    elif op == 'status':
        send(status(engines))
    elif op == 'models':
        send({'type': 'models', 'models': models.listing()})
    elif op == 'settings':
        settings(request, send)
    else:
        error(send, 'bad_request', f'unknown op: {op}')


def error(send, code, message):
    send({'type': 'error', 'code': code, 'message': message})


def status(engines):
    state = {}
    local_only = config.load().get('local_only')
    for name, engine in engines.items():
        if local_only and engine.host:      # not even a look at the cloud
            ok, why = False, 'is off (nothing leaves this laptop)'
        else:
            ok, why = router.check(engine)
        state[name] = {'ready': ok, 'why': why, 'model': engine.model()}
    return {'type': 'status', 'engines': state, 'models': models.listing(), 'settings': config.load(),
            'claude_suggested': config.SUGGESTED_CLAUDE, 'on_battery': models.on_battery()}


def settings(request, send):
    try:
        cfg = config.change(request['set']) if 'set' in request else config.load()
    except config.BadSetting as e:
        error(send, 'bad_setting', str(e))
        return
    send({'type': 'settings', 'settings': cfg})


def _checked(request):
    """(place, messages, context) or a ValueError that says what is wrong"""
    place = request.get('place') or 'dialer'
    messages, context = request.get('messages'), request.get('context') or []
    if place not in PLACES:
        raise ValueError(f'unknown place: {place}')
    if not isinstance(messages, list) or not messages or not all(isinstance(m, dict) for m in messages):
        raise ValueError('messages must be a list of {role, content}')
    if not isinstance(context, list) or not all(isinstance(c, dict) for c in context):
        raise ValueError('context must be a list of {path, text}')
    if not in_turns(messages):
        raise ValueError('there is no question in messages')
    if request.get('model') not in (None, *config.CLAUDE_MODELS):
        raise ValueError(f'unknown Claude model: {request.get("model")}')
    return place, messages, context


def ask(request, send, stop_event, engines):
    try:
        place, messages, context = _checked(request)
    except ValueError as e:
        error(send, 'bad_request', str(e))
        return
    try:
        usable, note = router.plan(config.load(), place, request.get('engine'), engines,
                                  request.get('model'))
    except router.NoEngine as e:
        error(send, 'no_engine', str(e))
        return
    began = time.monotonic()
    sent = [c['path'] for c in context if c.get('path')]
    for i, engine in enumerate(usable):
        if note:
            send({'type': 'note', 'text': note})
        send({'type': 'start', 'engine': engine.name, 'model': engine.model(), 'sent': sent})
        said = []

        def on_text(piece):
            said.append(1)
            send({'type': 'text', 'delta': piece})

        try:
            mine = without_local_answers(messages) if engine.host else messages
            model = engine.ask(in_turns(mine), context, on_text, stop_event)
        except EngineError as e:
            if said or i + 1 == len(usable):
                error(send, 'engine_failed', f'{engine.title}: {e}')
                return
            note = f'{engine.title} failed ({e}): answering with {usable[i + 1].title}'
            continue
        if not stop_event.is_set():
            send({'type': 'done', 'engine': engine.name, 'model': model or engine.model(),
                  'seconds': round(time.monotonic() - began, 1)})
        return
