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

function between(from, to) {            // minutes between two HH:MM times of the same day
  const [a, b] = [from, to].map(t => { const [h, m] = t.split(':').map(Number); return h * 60 + m; });
  return Math.max(0, b - a);
}

function timing(st, now) {
  // what was estimated against what the clock measured
  const end = st.finished || (st.state === 'doing' ? now : null);
  const parts = [];
  if (st.started && end) parts.push((st.finished ? 'took ' : 'running ') + minutes(between(st.started, end)));
  if (st.est) {
    parts.push(`estimated ${minutes(st.est)} at ${st.est_at}`);
    if (end) {
      const real = between(st.est_at, end);
      parts.push(st.finished ? `really ${minutes(real)} after that` : `${minutes(real)} so far`);
    }
  }
  return parts.join(' · ');
}

function stepRow(st, now) {
  const row = document.createElement('div'); row.className = 'step ' + st.state;
  const s = document.createElement('span'); s.className = 's'; s.textContent = st.state;
  const n = document.createElement('span'); n.textContent = st.name;
  const d = document.createElement('span'); d.className = 'n'; d.textContent = st.note || '';
  row.append(s, n, d);
  if (st.pct !== undefined) {
    const p = document.createElement('span'); p.className = 'p';
    const bar = document.createElement('span'); bar.className = 'mini';
    const fill = document.createElement('span'); fill.style.width = st.pct + '%'; bar.appendChild(fill);
    const t = document.createElement('span'); t.textContent = `${st.pct} %`;
    const m = document.createElement('span'); m.className = 'model';
    m.textContent = st.ran ? `ran on ${st.ran}` : `advice: ${st.model || '?'}`;
    m.title = `advice: ${st.model || '?'}`;
    p.append(bar, t, m); row.appendChild(p);
    const when = document.createElement('span'); when.className = 'when'; when.textContent = timing(st, now);
    row.appendChild(when);
  }
  return row;
}

function measured(p) {
  // all finished steps that had an estimate: the estimates added up against the clock
  const both = p.steps.filter(s => s.est && s.finished);
  if (!both.length) return '';
  const est = both.reduce((sum, s) => sum + s.est, 0);
  const real = both.reduce((sum, s) => sum + between(s.est_at, s.finished), 0);
  const factor = real ? (est / real).toFixed(1) : '?';
  return `Estimates against the clock: ${both.length} finished steps were estimated at ${minutes(est)} together ` +
    `and really took ${minutes(real)}: the estimates were ${factor}× too long.`;
}

async function progress() {
  try {
    const p = await (await fetch('progress.json', { cache: 'no-store' })).json();
    const done = p.steps.filter(s => s.state === 'done').length;
    const doing = p.steps.filter(s => s.state === 'doing');
    const pct = Math.round(p.steps.reduce((sum, s) => sum + (s.pct || 0), 0) / p.steps.length);
    $('#fill').style.width = pct + '%';
    $('#pct').textContent = `${pct} % · ${done} of ${p.steps.length} steps done`;
    $('#eta').textContent = p.run_started ? `running ${minutes(between(p.run_started, p.now))} (since ${p.run_started})` : '';
    $('#now').textContent = doing.length ? 'Now: ' + doing.map(s => s.name).join(' · ') : (p.status || '');
    $('#progress-at').textContent = `clock ${p.now} · changed ${p.updated}`;
    $('#measured').textContent = measured(p) + (p.first_estimate
      ? ` The first overall estimate (${p.first_estimate.at}): "${p.first_estimate.said}".` : '');
    const box = $('#steps'); box.innerHTML = '';
    p.steps.forEach(st => box.appendChild(stepRow(st, p.now)));
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
