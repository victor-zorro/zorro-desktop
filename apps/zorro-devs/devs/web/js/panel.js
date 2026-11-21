// The side panel: one item, with its status and the test state per device.
import { $, apply, el, post } from './dom.js';
import { address, state } from './state.js';

const STATUSES = ['open', 'doing', 'done'];
const STATES = ['ok', 'fail', 'untested'];
let shown = null;       // id of the item the panel is built for
let refresh = () => {};

export function setUpPanel(refreshNow) {
  refresh = refreshNow;
}

async function change(item, fields, what) {
  await apply(() => post(`api/items/${item.id}`, fields), what);
  refresh();
}

async function test(item, device, value) {
  await apply(() => post(`api/items/${item.id}/test`, { device, state: value }), `${device}: ${value}`);
  refresh();
}

function field(tag, item, name, label) {
  const box = el(tag, { 'data-field': name, 'aria-label': label, maxlength: tag === 'input' ? 120 : 4000,
    onchange: (event) => change(item, { [name]: event.target.value }, `${label} saved`) });
  if (tag === 'input') box.type = 'text';
  return box;
}

function segment(names, current, pick) {
  return el('div', { class: 'seg' }, ...names.map((name) => el('button',
    { class: `btn ${name}`, 'aria-pressed': String(name === current), onclick: () => pick(name) }, name)));
}

function testRow(item, device) {
  const made = (item.tests || {})[device] || { state: 'untested' };
  const name = device === state.here ? `${device} (this device)` : device;
  const stale = made.stale ? 'The app changed since: retest. ' : '';
  const when = made.at ? `${made.at.replace('T', ' ')} · ${made.version || '?'}` : '';
  return el('div', { class: 'test' }, el('span', { class: 'cut' }, name),
    segment(STATES, made.state, (value) => test(item, device, value)),
    stale || when ? el('span', { class: 'note' }, stale + when) : null);
}

function build(panel, item) {
  panel.replaceChildren(
    el('div', { class: 'top' }, el('span', { class: 'label' }),
      el('a', { class: 'btn', href: address(state.menu, state.app), 'aria-label': 'Close' }, '✕')),
    field('input', item, 'title', 'Title'),
    el('span', { class: 'label' }, 'Text'), field('textarea', item, 'text', 'Text'),
    el('span', { class: 'label' }, 'Test steps'), field('textarea', item, 'steps', 'Test steps'),
    el('span', { class: 'label' }, 'Status'), el('div', { class: 'status-seg' }),
    el('span', { class: 'label' }, 'Tested'), el('div', { class: 'tests' }));
  shown = item.id;
}

// Fill in what the laptop says now; a field you are typing in is left alone.
function fill(panel, item) {
  const where = [item.kind, item.app, item.category, item.check ? `check: ${item.check}` : ''];
  panel.querySelector('.top .label').textContent = where.filter(Boolean).join(' · ');
  for (const box of panel.querySelectorAll('[data-field]')) {
    if (box !== document.activeElement) box.value = item[box.dataset.field] || '';
  }
  panel.querySelector('.status-seg').replaceChildren(
    segment(STATUSES, item.status, (value) => change(item, { status: value }, `Status: ${value}`)));
  panel.querySelector('.tests').replaceChildren(...state.devices.map((d) => testRow(item, d)));
}

export function renderPanel() {
  const panel = $('#panel');
  const item = state.open && state.items.find((i) => i.id === state.open);
  panel.hidden = !item;
  if (!item) {
    shown = null;
    return;
  }
  if (shown !== item.id) build(panel, item);
  fill(panel, item);
}
