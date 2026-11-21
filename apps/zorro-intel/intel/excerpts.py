"""The excerpts that go along with a question: a few search hits, or one file, capped in size."""
import os
import subprocess

from . import folders, search

EXCERPT_CHARS = 1500        # one excerpt
TOTAL_CHARS = 6000          # everything sent with one question
TEXT_TYPES = ('.md', '.txt', '.org', '.rst')
NO_SEARCH = 'Search is not running: no files sent'


def build(hits, chosen, count, total=TOTAL_CHARS, each=EXCERPT_CHARS):
    """[{path, text}] from the best `count` hits inside the chosen folders, at most `total` characters"""
    out, left = [], total
    for hit in folders.allowed(hits, chosen):
        if len(out) >= count or left <= 0:
            break
        text = str(hit.get('snippet') or '').strip()[:min(each, left)]
        if not text:
            continue
        out.append({'path': hit['path'], 'text': text})
        left -= len(text)
    return out


def read_file(path, limit=TOTAL_CHARS):
    """the start of a text file or PDF, '' when it cannot be read"""
    lower = str(path).lower()
    try:
        if lower.endswith('.pdf'):
            done = subprocess.run(['pdftotext', '-l', '10', '-q', str(path), '-'],
                                  capture_output=True, text=True, timeout=20)
            return done.stdout[:limit].strip()
        if lower.endswith(TEXT_TYPES):
            with open(path, errors='replace') as f:
                return f.read(limit).strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return ''


def of_file(path, chosen, limit=TOTAL_CHARS):
    """one whole file as the context; [] when it lies outside the chosen folders or is unreadable"""
    if not folders.inside(path, chosen):
        return []
    text = read_file(path, limit)
    return [{'path': str(path), 'text': text}] if text else []


def gather(question, cfg, about=None, find=None):
    """(context, note): what to send with this question, and a line for the user or None"""
    chosen = cfg['folders']
    if about:
        context = of_file(about, chosen)
        return context, None if context else f'{os.path.basename(about)} could not be read: no files sent'
    if not chosen or cfg['excerpts'] <= 0:
        return [], None
    hits = (find or search.ask)(question)
    if hits is None:
        return [], NO_SEARCH
    return build(hits, chosen, cfg['excerpts']), None
