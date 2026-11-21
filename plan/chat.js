// The design area: notes (saved like the answers) and a chat answered through the laptop.
document.querySelectorAll('[data-notes]').forEach(host => {
  block(host, host.dataset.notes, [], false);
  host.querySelector('textarea').placeholder = 'What it must do, what annoys you in WinBox, routers you have, ideas…';
  host.querySelector('textarea').classList.add('tall');
});

function chatRow(m) {
  const row = document.createElement('div'); row.className = 'msg ' + m.role;
  const who = document.createElement('span'); who.className = 'label';
  who.textContent = m.role === 'user' ? 'you' : 'claude' + (m.busy ? ' · writing…' : '');
  const text = document.createElement('div'); text.textContent = m.content || (m.busy ? '…' : '');
  row.append(who, text);
  return row;
}

function chat(topic) {
  const box = $('#chat-' + topic), state = $('#chat-' + topic + '-state');
  const form = $('#ask-' + topic), input = $('#ask-' + topic + '-text');
  let seen = '';
  async function load() {
    try {
      const c = await (await fetch('api/chat/' + topic, { cache: 'no-store' })).json();
      const sig = JSON.stringify(c.messages);
      if (sig === seen) return;
      seen = sig;
      const atEnd = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
      box.innerHTML = '';
      if (!c.messages.length) box.appendChild(chatRow({ role: 'assistant', content: 'Nothing yet. Write your first idea or question below.' }));
      c.messages.forEach(m => box.appendChild(chatRow(m)));
      if (atEnd) box.scrollTop = box.scrollHeight;
    } catch (e) { state.textContent = 'The laptop does not answer'; }
  }
  async function send() {
    const text = input.value.trim();
    if (!text) return;
    state.textContent = 'sending…';
    try {
      const r = await fetch('api/chat/' + topic, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }) });
      if (r.status === 409) { state.textContent = 'Still answering the last one: wait a moment.'; return; }
      if (!r.ok) throw new Error(await r.text());
      input.value = ''; state.textContent = '';
      load();
    } catch (e) { state.textContent = 'Not sent: ' + (e.message || e); }
  }
  form.addEventListener('submit', e => { e.preventDefault(); send(); });
  input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
  load();
  setInterval(load, 2000);
}
chat('winbox');
