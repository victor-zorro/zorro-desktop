"""A design chat on the plan page. A question goes to zorro-ai (Claude through your plan),
the answer is written into the conversation as it arrives. Conversations live in the state
folder, next to the answers; one question at a time per topic."""
import json
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

ZAI = Path(__file__).resolve().parent.parent / 'apps' / 'zorro-ai' / 'zorro-ai'
LOCK = threading.Lock()
BUSY = set()
LIMIT_SECONDS = 300
BRIEFS = {
    'winbox': 'You help design a native Linux replacement for MikroTik WinBox (the router '
              'configuration tool): a GTK 3 Python app in the Zorro desktop style, talking to '
              'RouterOS. Be concrete and brief: propose, compare, ask one question at a time '
              'when a decision is needed. Plain text, short paragraphs and lists. You cannot '
              'read files or run anything; you only discuss the design.',
}


def path(state, topic):
    return Path(state) / f'chat-{topic}.json'


def load(state, topic):
    try:
        chat = json.loads(path(state, topic).read_text())
    except (OSError, ValueError):
        return {'messages': []}
    if topic not in BUSY:           # left over from a stop in the middle of an answer
        for m in chat.get('messages', []):
            m.pop('busy', None)
    return chat


def save(state, topic, chat):
    with LOCK:
        Path(state).mkdir(parents=True, exist_ok=True)
        tmp = path(state, topic).with_suffix('.tmp')
        tmp.write_text(json.dumps(chat, indent=1, ensure_ascii=False))
        tmp.replace(path(state, topic))


def prompt(topic, chat, notes):
    lines = [BRIEFS[topic], '']
    if notes:
        lines += ['The design notes so far:', notes[:6000], '']
    lines.append('The conversation so far:')
    for m in chat['messages'][-12:]:
        lines.append(f"{'User' if m['role'] == 'user' else 'You'}: {m['content'][:4000]}")
    lines.append('Answer the last message from the user.')
    return '\n'.join(lines)


def ask(state, topic, text, notes=''):
    """start an answer; False when this topic is still answering"""
    with LOCK:
        if topic in BUSY:
            return False
        BUSY.add(topic)
    chat = load(state, topic)
    now = datetime.now().isoformat(timespec='seconds')
    chat['messages'].append({'role': 'user', 'content': text, 'at': now})
    ask_text = prompt(topic, chat, notes)
    chat['messages'].append({'role': 'assistant', 'content': '', 'at': now, 'busy': True})
    save(state, topic, chat)
    threading.Thread(target=answer, args=(state, topic, chat, ask_text), daemon=True).start()
    return True


def answer(state, topic, chat, ask_text):
    reply = chat['messages'][-1]
    try:
        proc = subprocess.Popen([str(ZAI), 'ask', '--place', 'devs', ask_text], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        killer = threading.Timer(LIMIT_SECONDS, proc.kill)
        killer.start()
        saved = time.time()
        for piece in iter(lambda: proc.stdout.read(200), ''):
            reply['content'] += piece
            if time.time() - saved > 1:
                save(state, topic, chat)
                saved = time.time()
        killer.cancel()
        if proc.wait() != 0 and not reply['content']:
            reply['content'] = 'No answer: the AI could not be reached.'
    except Exception as e:      # noqa: BLE001  whatever happens, the chat must not stay "writing…"
        reply['content'] = reply['content'] or f'No answer: {e}'
    finally:
        reply.pop('busy', None)
        with LOCK:
            BUSY.discard(topic)
        try:
            save(state, topic, chat)
        except OSError:
            pass
