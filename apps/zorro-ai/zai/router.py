"""Which engine answers: the place's setting, a forced engine, or auto (Claude, Mistral, local)."""
from . import config, net

AUTO = ('claude', 'mistral', 'local')


class NoEngine(Exception):
    pass


def check(engine):
    """(usable now, why not)"""
    ok, why = engine.ready()
    if ok and engine.host and not net.reachable(engine.host):
        return False, 'not reachable'
    return ok, why


def _wanted(cfg, place, forced):
    """(engine name or auto, local model id or None)"""
    choice = forced or cfg['places'].get(place, 'auto')
    if not config.valid_engine(choice):
        raise NoEngine(f'unknown engine: {choice}')
    if choice.startswith('local:'):
        return 'local', choice.split(':', 1)[1]
    return choice, None


def plan(cfg, place, forced, engines):
    """(engines to try in order, a note or None). NoEngine when none can answer."""
    choice, model_id = _wanted(cfg, place, forced)
    skipped = []
    if cfg.get('local_only') and choice != 'local':
        if choice != 'auto':
            skipped.append(f'{engines[choice].title} is off (nothing leaves this laptop)')
        choice = 'local'
    usable = []
    for name in (AUTO if choice == 'auto' else (choice,)):
        engine = engines[name]
        if name == 'local' and model_id:
            engine = engine.use(model_id)
        ok, why = check(engine)
        if ok:
            usable.append(engine)
        elif not usable:
            skipped.append(f'{engine.title} {why}')
    if not usable:
        raise NoEngine('; '.join(skipped))
    note = f'{"; ".join(skipped)}: answering with {usable[0].title}' if skipped else None
    return usable, note
