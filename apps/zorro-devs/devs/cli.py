"""The command line: serve, fill, check, list, add."""
import argparse

from . import checks, devices, fill, server, store

PORT = 8098


def parser():
    top = argparse.ArgumentParser(prog='zorro-devs', description='DEVS: the catalogue, as a web page and here.')
    sub = top.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve', help='run the web page')
    serve.add_argument('--port', type=int, default=PORT)
    sub.add_parser('fill', help='first fill from the repo (safe to run again)')
    check = sub.add_parser('check', help='run the automatic checks')
    check.add_argument('name', nargs='?', choices=list(checks.CHECKS))
    listing = sub.add_parser('list', help='list items')
    listing.add_argument('--kind', choices=store.KINDS)
    listing.add_argument('--app')
    add = sub.add_parser('add', help='add an item')
    add.add_argument('kind', choices=store.KINDS)
    add.add_argument('title')
    add.add_argument('--app', default='')
    add.add_argument('--category', default='')
    add.add_argument('--text', default='')
    return top


def serve(args):
    devices.devices()
    web = server.make(args.port)
    print(f'zorro-devs: http://0.0.0.0:{args.port}/', flush=True)
    try:
        web.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        web.server_close()
    return 0


def run_fill(args):
    made, kept = fill.fill()
    print(f'{made} items made, {kept} already there')
    return 0


def run_checks(args):
    results = checks.run([args.name] if args.name else None)
    for name, result in results.items():
        print(f'{name:8} {"ok  " if result["ok"] else "FAIL"}  {result["detail"]}')
    return 0 if all(r['ok'] for r in results.values()) else 1


def run_list(args):
    for item in store.all_items(args.kind, args.app):
        print(f'{item["id"]:42.42} {item.get("kind", ""):8} {item.get("status", ""):5} '
              f'{item.get("app", ""):12.12} {item.get("title", "")}')
    return 0


def run_add(args):
    item = store.create(args.kind, args.title, app=args.app, category=args.category, text=args.text)
    print(item['id'])
    return 0


COMMANDS = {'serve': serve, 'fill': run_fill, 'check': run_checks, 'list': run_list, 'add': run_add}


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except store.Invalid as err:
        print(f'zorro-devs: {err}')
        return 2
