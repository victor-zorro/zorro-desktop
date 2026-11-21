"""zorro-ai: the one AI service every Zorro app asks.

  zorro-ai serve                  the service (zorro-ai.service), on $XDG_RUNTIME_DIR/zorro-ai.sock
  zorro-ai ask [--place P] [--engine E] TEXT...
                                  ask a question; the answer streams to the terminal
                                  P: dialer | intel | devs   E: claude | mistral | local | local:MODEL_ID
  zorro-ai status                 JSON: engines (ready, why), local models, settings
  zorro-ai models                 the local models: size, downloaded or not, measured speed
  zorro-ai pull MODEL_ID          download a local model (continues a download that was cut off)
  zorro-ai install-local          download llama.cpp's llama-server (no root needed)

Engines: claude (the claude program, your plan), mistral (Mistral's cloud, key in
~/.config/zorro-ai/mistral.key), local (llama.cpp on this laptop). auto = Claude, else Mistral,
offline local. Settings: ~/.config/zorro-ai/config.json.
"""
import argparse
import json
import signal
import sys
import threading

from . import client, install_local, models, service
from .download import DownloadError, fetch, progress_line
from .engines import all_engines
from .server import Server


def serve():
    server = Server(all_engines())
    server.bind()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: server.stop())
    print(f'zorro-ai: listening on {server.path}', flush=True)
    server.serve()
    return 0


def _replies(request):
    """from the service; when it does not run, answered in this process"""
    try:
        yield from client.replies(request)
    except client.NoService:
        yield from _direct(request)


def _direct(request):
    engines, got = all_engines(), []
    try:
        if request.get('op') == 'ask':
            print('zorro-ai: the service does not run, answering in this process', file=sys.stderr)
            service.handle(request, _show, threading.Event(), engines)
        else:
            service.handle(request, got.append, threading.Event(), engines)
    finally:
        engines['local'].shutdown()
    yield from got


def _show(reply):
    """Print one reply line of an answer; the exit code it means, or None to go on."""
    kind = reply.get('type')
    if kind == 'text':
        sys.stdout.write(reply['delta'])
        sys.stdout.flush()
    elif kind == 'note':
        print(f'zorro-ai: {reply["text"]}', file=sys.stderr)
    elif kind == 'start':
        files = f', {len(reply["sent"])} files sent' if reply.get('sent') else ''
        print(f'zorro-ai: {reply["engine"]} answers ({reply.get("model") or "?"}{files})', file=sys.stderr)
    elif kind == 'done':
        print(file=sys.stdout, flush=True)
        print(f'zorro-ai: answered by {reply["engine"]} ({reply.get("model")}) in {reply["seconds"]} s',
              file=sys.stderr)
        return 0
    elif kind == 'error':
        print(f'zorro-ai: {reply["code"]}: {reply["message"]}', file=sys.stderr)
        return 1
    return None


def ask(args):
    request = {'op': 'ask', 'place': args.place, 'engine': args.engine, 'context': [],
               'messages': [{'role': 'user', 'content': ' '.join(args.text)}]}
    code = 1
    try:
        for reply in _replies(request):
            shown = _show(reply)
            code = code if shown is None else shown
    except KeyboardInterrupt:
        return 130
    return code


def show_models():
    reply = next(_replies({'op': 'models'}), None) or {'models': []}
    for m in reply['models']:
        have = 'downloaded' if m['installed'] else '-'
        print(f'{m["id"]:22} {m["size"]:5.2f} GB  RAM {m["ram"]:4.1f} GB  {have:10}  {m["speed"]}')
        print(f'{"":22} {m["good_for"]}')
    return 0


def pull(model_id):
    m = models.find(model_id)
    if not m:
        print(f'zorro-ai: no model {model_id}; see: zorro-ai models', file=sys.stderr)
        return 1
    if models.installed(model_id):
        print(f'{model_id} is already downloaded')
        return 0
    try:
        fetch(m['url'], models.model_path(model_id), m.get('sha256'), progress_line(model_id))
    except DownloadError as e:
        print(f'\nzorro-ai: {e}', file=sys.stderr)
        return 1
    print(f'{model_id} downloaded to {models.model_path(model_id)}')
    return 0


def install():
    try:
        install_local.install()
    except (DownloadError, OSError) as e:
        print(f'zorro-ai: {e}', file=sys.stderr)
        return 1
    return 0


def parser():
    p = argparse.ArgumentParser(prog='zorro-ai', description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd')
    sub.add_parser('serve')
    a = sub.add_parser('ask')
    a.add_argument('--place', default='dialer', choices=service.PLACES)
    a.add_argument('--engine', default=None)
    a.add_argument('text', nargs='+')
    sub.add_parser('status')
    sub.add_parser('models')
    sub.add_parser('pull').add_argument('model_id')
    sub.add_parser('install-local')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.cmd == 'serve':
        return serve()
    if args.cmd == 'ask':
        return ask(args)
    if args.cmd == 'status':
        print(json.dumps(next(_replies({'op': 'status'}), None), indent=1))
        return 0
    if args.cmd == 'models':
        return show_models()
    if args.cmd == 'pull':
        return pull(args.model_id)
    if args.cmd == 'install-local':
        return install()
    print(__doc__.strip())
    return 0
