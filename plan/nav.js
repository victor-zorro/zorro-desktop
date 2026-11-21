// The menu (one page at a time, by the address after #) and the status bar of the run.
const VIEWS = [...document.querySelectorAll('main > section')];

function show() {
  const id = (location.hash || '#progress').slice(1);
  const view = VIEWS.find(v => v.id === id) || VIEWS[0];
  VIEWS.forEach(v => { v.hidden = v !== view; });
  document.querySelectorAll('#menu a').forEach(a => {
    a.setAttribute('aria-current', a.getAttribute('href') === '#' + view.id ? 'page' : 'false');
  });
  document.querySelector('main').scrollTop = 0;
}
window.addEventListener('hashchange', show);
show();

function minutes(m) {
  return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m} min`;
}

function stepRow(st) {
  const row = document.createElement('div'); row.className = 'step ' + st.state;
  const s = document.createElement('span'); s.className = 's'; s.textContent = st.state;
  const n = document.createElement('span'); n.textContent = st.name;
  const d = document.createElement('span'); d.className = 'n'; d.textContent = st.note || '';
  row.append(s, n, d);
  if (st.pct !== undefined) {
    const p = document.createElement('span'); p.className = 'p';
    const bar = document.createElement('span'); bar.className = 'mini';
    const fill = document.createElement('span'); fill.style.width = st.pct + '%'; bar.appendChild(fill);
    const t = document.createElement('span');
    t.textContent = `${st.pct} %` + (st.eta ? ` · about ${minutes(st.eta)}` : '');
    const m = document.createElement('span'); m.className = 'model'; m.textContent = st.model || '';
    p.append(bar, t, m); row.appendChild(p);
  }
  return row;
}

async function progress() {
  try {
    const p = await (await fetch('progress.json', { cache: 'no-store' })).json();
    const done = p.steps.filter(s => s.state === 'done').length;
    const doing = p.steps.filter(s => s.state === 'doing');
    const pct = Math.round(p.steps.reduce((sum, s) => sum + (s.pct || 0), 0) / p.steps.length);
    const left = p.eta_total !== undefined ? p.eta_total : p.steps.reduce((sum, s) => sum + (s.eta || 0), 0);
    $('#fill').style.width = pct + '%';
    $('#pct').textContent = `${pct} % · ${done} of ${p.steps.length} steps done`;
    $('#eta').textContent = left ? `about ${minutes(left)} to go` : 'finished';
    $('#now').textContent = doing.length ? 'Now: ' + doing.map(s => s.name).join(' · ') : (p.status || '');
    $('#progress-at').textContent = 'updated ' + p.updated;
    const box = $('#steps'); box.innerHTML = '';
    p.steps.forEach(st => box.appendChild(stepRow(st)));
  } catch (e) {
    $('#now').textContent = 'The laptop does not answer';
  }
}
progress();
setInterval(progress, 10000);

async function review() {
  try {
    const r = await (await fetch('review.json', { cache: 'no-store' })).json();
    const all = [...r.before, ...r.after];
    const fixed = all.filter(f => f.state === 'fixed').length;
    $('#rev-count').textContent = `Review before: ${r.before.length} findings, ${fixed} fixed` +
      (r.after.length ? ` · review after: ${r.after.length}` : '');
    const box = $('#findings'); box.innerHTML = '';
    all.forEach(f => box.appendChild(stepRow({
      state: f.state === 'fixed' ? 'done' : f.level === 'critical' || f.level === 'high' ? 'problem' : 'todo',
      name: f.title, note: `${f.area} · ${f.level} · ${f.state}` })));
  } catch (e) { /* the next round tries again */ }
}
review();
setInterval(review, 15000);
