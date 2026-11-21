"""zorro-intel: Intelligence, search and AI over the folders you chose.

  zorro-intel                 open the window (a second start shows the one that is open)
  zorro-intel --page NAME     open it on a page: ask | search | engines | models | folders | key | about

Answers come from zorro-ai (Claude, Mistral cloud or a model on this laptop); the search is
zorro-search, on this laptop. Only files in the folders you chose are shown or sent.
"""
import sys

PAGES = {'ask': 'Ask', 'search': 'Search', 'engines': 'Engines', 'models': 'Local models',
         'folders': 'Folders', 'key': 'Mistral key', 'about': 'About / privacy'}      # address: menu name


def page_of(argv):
    """the page asked for, None for none; ValueError when the arguments are wrong"""
    if not argv:
        return None
    if argv[0].startswith('--page='):
        name, rest = argv[0].split('=', 1)[1], argv[1:]
    elif argv[0] == '--page' and len(argv) > 1:
        name, rest = argv[1], argv[2:]
    else:
        raise ValueError(f'unknown argument: {argv[0]}')
    if rest or name not in PAGES:
        raise ValueError('pages: ' + ' | '.join(PAGES))
    return name


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ('-h', '--help'):
        print(__doc__.strip())
        return 0
    try:
        page = page_of(argv)
    except ValueError as e:
        print(f'zorro-intel: {e}', file=sys.stderr)
        return 2
    from .app import App
    return App().run(['zorro-intel'] + (['--page', page] if page else []))
