"""Claude through the `claude` CLI on PATH (the user's plan): print mode, text only, no tools."""
import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading

from .. import config
from . import EngineError, context_text, on_stop

SYSTEM = ('You are the assistant built into a Linux desktop. Answer the question directly, in plain '
          'text or simple Markdown, in the language of the question. You have no tools and cannot read '
          'files: use only the conversation and the excerpts given in it.')
FLAGS = ['-p', '--output-format', 'stream-json', '--verbose', '--include-partial-messages',
         '--tools', '', '--strict-mcp-config', '--disable-slash-commands', '--no-session-persistence',
         '--setting-sources', '']      # none of your own Claude hooks, plugins or memory
DEADLINE = 600          # seconds one answer may take


def prompt_text(messages, context):
    """(system, prompt): system messages join the system prompt, the rest becomes one text"""
    system = [SYSTEM] + [str(m.get('content', '')) for m in messages if m.get('role') == 'system']
    turns = [m for m in messages if m.get('role') != 'system']
    if len(turns) == 1:
        talk = str(turns[0].get('content', ''))
    else:
        names = {'user': 'User', 'assistant': 'Assistant'}
        talk = '\n\n'.join(f'{names.get(m.get("role"), "User")}: {m.get("content", "")}' for m in turns)
        talk = 'The conversation so far; answer the last message.\n\n' + talk
    return '\n\n'.join(system), context_text(context) + talk


def end_group(proc):
    """Stop the process and what it started: TERM, then KILL after two seconds."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, sig)
        except OSError:
            return
        try:
            proc.wait(2)
            return
        except subprocess.TimeoutExpired:
            continue


class Claude:
    name, title, host = 'claude', 'Claude', 'api.anthropic.com'

    def __init__(self, program='claude', choice=None):
        self.program = program
        self.choice = choice if choice in config.CLAUDE_MODELS else 'default'

    def use(self, choice):
        """the same engine, held to one model choice (haiku, sonnet, opus or default)"""
        return Claude(self.program, choice)

    def model(self):
        return 'claude' if self.choice == 'default' else f'claude {self.choice}'

    def ready(self):
        if not shutil.which(self.program):
            return False, f'is not installed (no {self.program} program on PATH)'
        return True, ''

    def ask(self, messages, context, on_text, stop_event):
        system, prompt = prompt_text(messages, context)
        wanted = [] if self.choice == 'default' else ['--model', self.choice]
        with tempfile.TemporaryDirectory(prefix='zorro-ai-') as empty, tempfile.TemporaryFile('w+') as errors:
            try:
                proc = subprocess.Popen([self.program, *FLAGS, *wanted, '--system-prompt', system], cwd=empty,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=errors, text=True, start_new_session=True)
            except OSError as e:
                raise EngineError(f'could not start {self.program}: {e}') from e
            state = {'model': None, 'said': False, 'error': None}
            try:
                with on_stop(stop_event, lambda: end_group(proc)):
                    out = self._talk(proc, prompt, on_text, state)
            finally:
                end_group(proc)
                _close(proc.stdin, proc.stdout)
            errors.seek(0)
            err = errors.read()
        if stop_event.is_set():
            return state['model']
        if state['error'] or proc.returncode:
            raise EngineError(state['error'] or (err or out).strip()[-300:] or f'claude ended with {proc.returncode}')
        return state['model']

    def _talk(self, proc, prompt, on_text, state):
        """Feed the prompt, read the stream; returns the output that was no JSON."""
        call_off = _deadline(proc, state)
        stray = []
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
            for line in proc.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
                    stray.append(line)
                    continue
                if isinstance(event, dict):
                    read_event(event, on_text, state)
            proc.wait(5)
        except (OSError, subprocess.TimeoutExpired) as e:
            state['error'] = state['error'] or f'claude: {e}'
        finally:
            call_off()
        return ''.join(stray)


def _close(*pipes):
    for pipe in pipes:
        try:
            pipe.close()
        except OSError:
            pass


def _deadline(proc, state):
    """End the process when it takes longer than DEADLINE; returns the function that calls this off."""
    def too_long():
        state['error'] = f'no full answer within {DEADLINE} seconds'
        end_group(proc)

    timer = threading.Timer(DEADLINE, too_long)
    timer.daemon = True
    timer.start()
    return timer.cancel


def read_event(event, on_text, state):
    """One line of `claude --output-format stream-json`."""
    kind = event.get('type')
    if kind == 'system' and event.get('subtype') == 'init':
        state['model'] = event.get('model') or state['model']
    elif kind == 'stream_event':
        inner = event.get('event') or {}
        delta = inner.get('delta') or {}
        if inner.get('type') == 'content_block_delta' and delta.get('type') == 'text_delta':
            state['said'] = True
            on_text(delta.get('text', ''))
    elif kind == 'result':
        text = event.get('result') or ''
        if event.get('is_error'):
            state['error'] = str(text or event.get('subtype') or 'claude reported an error')[:300]
        elif text and not state['said']:
            state['said'] = True
            on_text(text)
