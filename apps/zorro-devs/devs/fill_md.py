"""Just enough Markdown reading for the first fill: headings, bullets, table rows, paragraphs."""
import re

BULLET = re.compile(r'(?:[-*]|\d+\.) +(.*)')
CLAUSE_END = re.compile(r'[:(;,·=]|\.(?=\s|$)| - | — ')


def plain(text):
    return ' '.join(text.replace('**', '').replace('`', '').split())


def classify(line):
    if not line.strip():
        return 'blank', ''
    if line.startswith('#'):
        level = len(line) - len(line.lstrip('#'))
        return ('h1' if level == 1 else 'heading'), line.lstrip('#').strip()
    bullet = BULLET.match(line)
    if bullet:
        return 'bullet', bullet.group(1).strip()
    if line.startswith('|'):
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if all(re.fullmatch(r':?-+:?', c) for c in cells):
            return 'rule', ''
        return 'row', cells
    return 'more', line.strip()


def blocks(text):
    """The text as a list of (kind, value). Code blocks are left out; a table's first
    row comes as 'header'; lines that go on join the bullet or paragraph before them."""
    out, in_code = [], False
    for line in text.splitlines():
        if line.lstrip().startswith('```'):
            in_code = not in_code
            continue
        if in_code:
            continue
        kind, value = classify(line)
        last = out[-1][0] if out else 'blank'
        if kind == 'more' and last in ('bullet', 'para'):
            out[-1] = (last, out[-1][1] + ' ' + value)
        elif kind == 'more':
            out.append(('para', value))
        elif kind == 'row' and last not in ('row', 'header', 'rule'):
            out.append(('header', value))
        else:
            out.append((kind, value))
    return [b for b in out if b[0] not in ('blank', 'rule')]


def shorten(text, most=60):
    if len(text) <= most:
        return text
    return text[:most].rsplit(' ', 1)[0].rstrip(' ,;:(') + '…'


def first_clause(text):
    """The start of a sentence, up to its first break: a short title."""
    is_code = text.startswith('`')
    text = plain(text)
    end = CLAUSE_END.search(text, 8)
    clause = text[:end.start()] if end else text
    clause = shorten(clause.strip().rstrip('.:;,'))
    return clause if is_code else clause[:1].upper() + clause[1:]


def bullet_title(bullet):
    """A bullet's own bold name when it has one, else its first clause."""
    bold = re.match(r'\*\*(.+?)\*\*', bullet)
    if bold and bold.group(1)[:1].isupper():
        return shorten(plain(bold.group(1)).rstrip('.:'))
    return first_clause(bullet)


def sentences(paragraph):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+(?=[A-Z`"])', paragraph) if s.strip()]
