// The page of one kind (+ app): filter line, the Add field, the list in its own box.
import { $, apply, el, post } from './dom.js';
import { address, entry, kind, state } from './state.js';

const SIGN = { ok: '✓', fail: '✕', untested: '○' };

export function mark(test, device) {
  const state_ = test && SIGN[test.state] ? test.state : 'untested';
  const stale = Boolean(test && test.stale);
  const what = stale ? `${device}: ${state_}, retest` : `${device}: ${state_}`;
  return el('span', { class: `mark ${stale ? 'stale' : state_}`, title: what }, SIGN[state_],
    stale ? el('small', {}, 'retest') : null);
}

function visible(item) {
  const words = state.search.trim().toLowerCase();
  const text = `${item.title} ${item.text} ${item.category} ${item.app}`.toLowerCase();
  const tests = item.tests || {};
  const here = tests[state.here];
  if (words && !text.includes(words)) return false;
  if (state.onlyHere && here && here.state !== 'untested') return false;
  if (state.onlyStale && !Object.values(tests).some((t) => t.stale)) return false;
  return true;
}

function row(item) {
  const marks = state.devices.map((d) => mark((item.tests || {})[d], d));
  return el('a', { class: 'row', role: 'listitem', href: address(state.menu, state.app, item.id),
    'aria-current': item.id === state.open ? 'true' : null },
    el('span', { class: 'cut' }, item.title),
    el('span', { class: 'cut cat' }, state.app === null && item.app ? `${item.app} · ${item.category}` : item.category),
    el('span', { class: `status ${item.status}` }, item.status),
    el('span', { class: 'marks' }, ...marks));
}

function head() {
  return el('div', { class: 'row head label' }, el('span', {}, 'Title'), el('span', { class: 'cat' }, 'Category'),
    el('span', {}, 'Status'), el('span', { class: 'marks' }, ...state.devices.map((d) => el('span', { title: d }, d))));
}

export function renderItems() {
  const list = $('#list');
  const top = list.scrollTop;
  const shown = state.items.filter(visible);
  list.style.setProperty('--marks', `${state.devices.length * 90}px`);
  const rows = shown.length ? shown.map(row) : [el('div', { class: 'empty' }, 'Nothing here.')];
  list.replaceChildren(head(), ...rows);
  list.scrollTop = top;
}

async function add(field, refresh) {
  const title = field.value.trim();
  if (!title) return;
  const made = await apply(() => post('api/items', { kind: kind(), title, app: state.app || '' }),
    `Added to ${entry().name}: ${title}`);
  if (made) field.value = '';
  refresh();
}

function toggle(button, name) {
  state[name] = !state[name];
  button.setAttribute('aria-pressed', String(state[name]));
  renderItems();
}

export function setUpItems(refresh) {
  $('#search').addEventListener('input', (event) => { state.search = event.target.value; renderItems(); });
  $('#only-here').addEventListener('click', (event) => toggle(event.currentTarget, 'onlyHere'));
  $('#only-stale').addEventListener('click', (event) => toggle(event.currentTarget, 'onlyStale'));
  $('#add').addEventListener('keydown', (event) => { if (event.key === 'Enter') add(event.target, refresh); });
}
