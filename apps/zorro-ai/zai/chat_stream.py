"""One streaming chat-completions call (the OpenAI shape that Mistral and llama-server share)."""
import http.client
import json
import os
import socket
import urllib.parse

from .engines import EngineError, on_stop

AGENT = 'zorro-ai/1.0'


def _connect(url, timeout):
    u = urllib.parse.urlsplit(url)
    kind = http.client.HTTPSConnection if u.scheme == 'https' else http.client.HTTPConnection
    return kind(u.hostname, u.port, timeout=timeout), u.path or '/'


def _second_handle(conn):
    """Our own handle on the connection: http.client lets go of its socket once the answer starts."""
    conn.connect()
    return socket.socket(fileno=os.dup(conn.sock.fileno()))


def _hang_up(handle):
    try:
        handle.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def _delta_text(event):
    """(text, model) of one stream event"""
    choices = event.get('choices') or [{}]
    content = (choices[0].get('delta') or {}).get('content')
    if isinstance(content, list):       # Mistral may send a list of {type: text, text: …}
        content = ''.join(c.get('text', '') for c in content if isinstance(c, dict))
    return content or '', event.get('model')


def _error_text(resp):
    body = resp.read(2000).decode('utf-8', 'replace')
    try:
        detail = json.loads(body)
        detail = detail.get('message') or (detail.get('error') or {}).get('message') or body
    except (ValueError, AttributeError):
        detail = body
    return f'HTTP {resp.status}: {str(detail).strip()[:200]}'


def stream_chat(url, body, on_text, stop_event, key=None, timeout=120):
    """POST body with stream=true and call on_text for each piece; returns the last event seen.
    Setting stop_event closes the connection, which also stops the far side."""
    headers = {'Content-Type': 'application/json', 'Accept': 'text/event-stream', 'User-Agent': AGENT}
    if key:
        headers['Authorization'] = f'Bearer {key}'
    conn, path = _connect(url, timeout)
    last, handle = {}, None
    try:
        handle = _second_handle(conn)
        with on_stop(stop_event, lambda: _hang_up(handle)):
            conn.request('POST', path, json.dumps({**body, 'stream': True}), headers)
            resp = conn.getresponse()
            if resp.status != 200:
                raise EngineError(_error_text(resp))
            for raw in resp:
                line = raw.decode('utf-8', 'replace').strip()
                if not line.startswith('data:'):
                    continue
                data = line[5:].strip()
                if data == '[DONE]':
                    break
                event = json.loads(data)
                text, _model = _delta_text(event)
                last = {**last, **{k: v for k, v in event.items() if k in ('model', 'usage', 'timings')}}
                if text:
                    on_text(text)
    except (OSError, http.client.HTTPException, ValueError) as e:
        if not stop_event.is_set():
            raise EngineError(f'{type(e).__name__}: {e}') from e
    finally:
        conn.close()
        if handle:
            handle.close()
    return last
