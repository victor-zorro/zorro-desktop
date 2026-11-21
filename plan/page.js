const APPS = [
  { id: 'desktop', name: 'Desktop', kind: 'moved', what: 'Use: how it looks and how you work',
    items: ['Desktop', 'Look', 'Dialer', 'Wallpaper', 'Info circle', 'Windows', 'Text & colours', 'Login look', 'Face unlock', 'Shortcuts'] },
  { id: 'system', name: 'System', kind: 'moved', what: 'Settings and hardware',
    items: ['Network', 'Audio', 'Power', 'Hardware', 'ThinkPad keys', 'Bluetooth (+ Music shortcut checkbox)', 'Printers', 'System info'] },
  { id: 'devs', name: 'DEVS', kind: 'new', what: 'Everything built and to be built',
    items: ['Bugs, feature wishes, backlog', 'Existing features too', 'Sorted by category and main app', 'Checked and tested, per device', 'A web page served from the laptop: open it on any screen', 'This plan lives in it', 'On the laptop now, to the cloud later'] },
  { id: 'connect', name: 'Connect', kind: 'new', what: 'Set up and link devices',
    items: ['Transfer: send and receive settings, apps, files', 'Bootstrap a new machine', 'Install apps (extras)', 'NetBird link'] },
  { id: 'intel', name: 'Intelligence', kind: 'new', apart: true, what: 'Search + AI · not in the switcher',
    items: ['Its own app, with a clear interface of its own', 'Search notes and documents by meaning', 'AI answers from your own files', 'Its chat is built into the Dialer (the AI part)', 'Engine: your choice (Claude / Mistral)'] },
];
const QS = [
  { id: 'mistral-where', q: 'Mistral as fallback: where does it run?', opts: ['On the laptop (offline, private)', "Mistral's cloud (API key, needs internet)", 'Both'] },
  { id: 'mistral-size', q: 'If on the laptop: which size?', opts: ['Small: lighter, more mistakes', 'Medium (7–8B): better, ~5 GB RAM'] },
  { id: 'ai-read', q: 'What may the AI read?', multi: true, opts: ['Notes', 'Documents', 'This repo', 'Everything in home', 'Only folders I choose'] },
  { id: 'ai-act', q: 'In DEVS, may the AI act?', opts: ['Change code + commit after I approve', 'Only suggest'] },
  { id: 'ai-devs', q: 'What does the AI do in DEVS?', multi: true, opts: ['Sort new items into category / app', 'Write test steps', 'Work on bugs', 'Fill the catalogue from the repo'] },
  { id: 'offline', q: 'Must the AI ever work fully offline?', opts: ['Yes', 'No, Claude online is fine'] },
  { id: 'devs-devices', q: 'DEVS: which devices get a test status?', multi: true, opts: ['ThinkPad', 'VM', 'Each new device after a Transfer'] },
  { id: 'devs-fill', q: 'DEVS: first pass from the repo (every app and its features as items)?', opts: ['Yes, I check them after', 'No, I fill it myself'] },
  { id: 'devs-test', q: 'DEVS: how is "tested" set?', opts: ['A tick by hand', 'Tick by hand + automatic checks where possible'] },
  { id: 'intel-dialer', q: 'Intelligence vs the Dialer\'s Notes search', opts: ['Replaces it', 'Sits next to it'] },
  { id: 'messages', q: 'Messages & notifications in the Dialer', opts: ['One list, newest first', 'Two tabs in one part'] },
  { id: 'dial-ai', q: 'The Dialer\'s AI part shows…', opts: ['Input + the last answer', 'A short chat history'] },
  { id: 'names', q: 'Names of the two Settings apps', opts: ['Desktop + System', 'Other (note)'] },
  { id: 'review-when', q: 'Review before: when?', opts: ['Now, while we plan', 'Right before the build starts'] },
  { id: 'bootstrap', q: 'Connect → bootstrap a new machine', multi: true, opts: ['Show the one-line command', 'Make a USB installer'] },
];

const $ = (s, el = document) => el.querySelector(s);
const answers = {};            // id -> {pick: [], note: ''}
let db = null;

// ---- apps
const sw = $('#switcher'), cards = $('#appcards');
APPS.forEach(a => {
  const b = document.createElement('button');
  b.textContent = a.name; b.setAttribute('aria-pressed', 'false'); b.dataset.id = a.id;
  b.onclick = () => {
    const on = b.getAttribute('aria-pressed') !== 'true';
    sw.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', 'false'));
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
    cards.querySelectorAll('.appcard').forEach(c => c.dataset.dim = on && c.dataset.id !== a.id ? '1' : '0');
  };
  if (!a.apart) sw.appendChild(b);
  const c = document.createElement('div');
  c.className = 'card appcard'; c.dataset.id = a.id;
  c.innerHTML = `<span class="chip ${a.kind} tag">${a.apart ? 'new app · apart' : a.kind === 'new' ? 'new app' : 'from Settings'}</span>
    <h3></h3><p class="dim"></p><ul>${a.items.map(() => '<li></li>').join('')}</ul>`;
  $('h3', c).textContent = a.name; $('p', c).textContent = a.what;
  c.querySelectorAll('li').forEach((li, i) => li.textContent = a.items[i]);
  cards.appendChild(c);
});

// ---- dialer ring
(function ring() {
  const parts = [['Apps', ''], ['Music', ''], ['Notes', ''], ['AI', 'new'], ['Messages', 'merged'], ['System', ''], ['Files', '']];
  const svg = $('#ring'), cx = 210, cy = 210, r1 = 92, r2 = 180, n = parts.length, gap = 0.03;
  const ns = 'http://www.w3.org/2000/svg';
  const pt = (r, a) => [cx + r * Math.sin(a), cy - r * Math.cos(a)];
  parts.forEach(([name, kind], i) => {
    const a0 = i / n * 2 * Math.PI + gap, a1 = (i + 1) / n * 2 * Math.PI - gap;
    const [x0, y0] = pt(r2, a0), [x1, y1] = pt(r2, a1), [x2, y2] = pt(r1, a1), [x3, y3] = pt(r1, a0);
    const p = document.createElementNS(ns, 'path');
    p.setAttribute('d', `M${x0},${y0} A${r2},${r2} 0 0 1 ${x1},${y1} L${x2},${y2} A${r1},${r1} 0 0 0 ${x3},${y3} Z`);
    p.setAttribute('fill', kind === 'new' ? 'rgba(25,230,255,.14)' : '#0b0f15');
    p.setAttribute('stroke', kind === 'new' ? '#19e6ff' : kind === 'merged' ? '#d8d8de' : 'rgba(255,255,255,.18)');
    if (kind === 'merged') p.setAttribute('stroke-dasharray', '4 3');
    svg.appendChild(p);
    const [tx, ty] = pt((r1 + r2) / 2, (a0 + a1) / 2);
    const t = document.createElementNS(ns, 'text');
    t.setAttribute('x', tx); t.setAttribute('y', ty + (kind ? -2 : 4)); t.setAttribute('text-anchor', 'middle');
    t.setAttribute('fill', kind === 'new' ? '#19e6ff' : '#d8d8de'); t.setAttribute('font-size', '13'); t.setAttribute('font-weight', '700');
    t.textContent = name; svg.appendChild(t);
    if (kind) {
      const s = document.createElementNS(ns, 'text');
      s.setAttribute('x', tx); s.setAttribute('y', ty + 13); s.setAttribute('text-anchor', 'middle');
      s.setAttribute('fill', '#6f7079'); s.setAttribute('font-size', '10'); s.textContent = kind === 'merged' ? '+ notifications' : 'new';
      svg.appendChild(s);
    }
  });
  const c = document.createElementNS(ns, 'circle');
  c.setAttribute('cx', cx); c.setAttribute('cy', cy); c.setAttribute('r', r1 - 14);
  c.setAttribute('fill', '#05070a'); c.setAttribute('stroke', 'rgba(255,255,255,.18)'); svg.appendChild(c);
  const t = document.createElementNS(ns, 'text');
  t.setAttribute('x', cx); t.setAttribute('y', cy + 9); t.setAttribute('text-anchor', 'middle');
  t.setAttribute('fill', '#d8d8de'); t.setAttribute('font-size', '26'); t.setAttribute('font-weight', '700');
  t.textContent = '10:42'; svg.appendChild(t);
})();

// ---- reactions (per section) and questions
function block(host, id, opts, multi) {
  host.innerHTML = '';
  const o = document.createElement('div'); o.className = 'opts';
  opts.forEach(label => {
    const b = document.createElement('button'); b.className = 'opt'; b.type = 'button';
    b.textContent = label; b.setAttribute('aria-pressed', 'false');
    b.onclick = () => {
      const a = answers[id] || (answers[id] = { pick: [], note: '' });
      if (multi) a.pick = a.pick.includes(label) ? a.pick.filter(x => x !== label) : [...a.pick, label];
      else a.pick = a.pick.includes(label) ? [] : [label];
      paint(id); save(id);
    };
    o.appendChild(b);
  });
  const ta = document.createElement('textarea'); ta.id = 'note-' + id;
  ta.placeholder = 'A note or reaction (optional)';
  let t = null;
  ta.oninput = () => {
    const a = answers[id] || (answers[id] = { pick: [], note: '' });
    a.note = ta.value; clearTimeout(t); t = setTimeout(() => save(id), 800);
    status(id, 'typing…');
  };
  const s = document.createElement('div'); s.className = 'saved'; s.id = 'saved-' + id;
  host.append(o, ta, s);
}
document.querySelectorAll('.react').forEach(h => {
  const lbl = document.createElement('span'); lbl.className = 'label'; lbl.textContent = 'your reaction';
  const box = document.createElement('div'); box.style.display = 'grid'; box.style.gap = '8px';
  h.append(lbl, box);
  block(box, h.dataset.r, ['Good like this', 'Change something (note)'], false);
  box.dataset.id = h.dataset.r;
});
QS.forEach((q, i) => {
  const el = document.createElement('div'); el.className = 'q'; el.id = 'q-' + q.id;
  el.innerHTML = `<div class="qh"><span class="qn">${String(i + 1).padStart(2, '0')}</span><h3></h3>${q.multi ? '<span class="dim" style="font-size:12px">pick any</span>' : ''}</div><div></div>`;
  $('h3', el).textContent = q.q;
  block(el.lastElementChild, q.id, q.opts, q.multi);
  $('#qs').appendChild(el);
});

function paint(id) {
  const a = answers[id] || { pick: [], note: '' };
  const ta = document.getElementById('note-' + id);
  if (!ta) return;
  const host = ta.parentElement;
  host.querySelectorAll('.opt').forEach(b => b.setAttribute('aria-pressed', a.pick.includes(b.textContent) ? 'true' : 'false'));
  if (document.activeElement !== ta) ta.value = a.note || '';
  const q = document.getElementById('q-' + id);
  if (q) q.dataset.answered = (a.pick.length || (a.note || '').trim()) ? '1' : '0';
  const n = QS.filter(x => { const v = answers[x.id]; return v && (v.pick.length || (v.note || '').trim()); }).length;
  $('#count').textContent = `${n} / ${QS.length} answered`;
}
function status(id, text, cls) {
  const s = document.getElementById('saved-' + id);
  if (s) { s.textContent = text; s.className = 'saved' + (cls ? ' ' + cls : ''); }
}
async function save(id) {
  const a = answers[id];
  try {
    const r = await fetch('api/answers/' + encodeURIComponent(id), { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pick: a.pick, note: a.note || '' }) });
    if (!r.ok) throw new Error((await r.text()) || r.status);
    status(id, 'saved on the laptop', 'ok');
  } catch (e) { status(id, 'not saved: ' + (e && e.message || e) + ' (is the laptop on?)', 'err'); }
}
QS.forEach(q => paint(q.id));

// copy
$('#copy').onclick = () => {
  const text = $('#cmd').textContent;
  navigator.clipboard.writeText(text).then(() => { $('#copy').textContent = 'Copied'; },
    () => { const r = document.createRange(); r.selectNodeContents($('#cmd')); const s = getSelection(); s.removeAllRanges(); s.addRange(r); });
};

// ---- storage: answers live on the laptop (plan/serve.py); refreshed every 5 s
async function load() {
  const note = $('#dbnote');
  try {
    const r = await fetch('api/answers', { cache: 'no-store' });
    const all = await r.json();
    note.hidden = true;
    for (const [id, v] of Object.entries(all)) {
      answers[id] = { pick: Array.isArray(v.pick) ? v.pick.map(String) : [], note: String(v.note || '') };
      paint(id);
    }
  } catch (e) {
    note.hidden = false;
    note.textContent = 'The laptop does not answer: answers made now are not saved.';
  }
}
load();
setInterval(load, 5000);

// ---- progress of the run (plan/progress.json, written by Claude)
async function progress() {
  try {
    const p = await (await fetch('progress.json', { cache: 'no-store' })).json();
    $('#progress-at').textContent = 'Updated ' + p.updated + '. Refreshes by itself.';
    const box = $('#steps'); box.innerHTML = '';
    p.steps.forEach(st => {
      const row = document.createElement('div'); row.className = 'step ' + st.state;
      const s = document.createElement('span'); s.className = 's'; s.textContent = st.state;
      const n = document.createElement('span'); n.textContent = st.name;
      const d = document.createElement('span'); d.className = 'n'; d.textContent = st.note || '';
      row.append(s, n, d); box.appendChild(row);
    });
  } catch (e) { /* the next round tries again */ }
}
progress();
setInterval(progress, 10000);
