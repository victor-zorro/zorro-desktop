// The menu (always there) and the submenu: the apps, at most seven entries at a time.
import { $, el } from './dom.js';
import { MENU, address, kind, state } from './state.js';

const MOST = 7;

function link(name, count, href, current) {
  return el('a', { class: 'entry', href, 'aria-current': current ? 'page' : null },
    el('span', { class: 'name' }, name), count === null ? null : el('span', { class: 'n' }, String(count)));
}

export function renderMenu() {
  const entries = MENU.map((m) => link(m.name, m.kind ? state.kinds[m.kind] ?? '' : null,
    address(m.id), m.id === state.menu));
  $('#menu-list').replaceChildren(...entries);
}

// The apps in pages: the first starts with All, the others with Back; More leads on.
function pages(apps) {
  if (apps.length + 1 <= MOST) return [apps];
  const out = [];
  let rest = apps;
  for (let n = 0; n < 20 && rest.length; n++) {
    const fits = rest.length <= MOST - 1 ? MOST - 1 : MOST - 2;
    out.push(rest.slice(0, fits));
    rest = rest.slice(fits);
  }
  return out;
}

function step(name, to) {
  return el('button', { class: 'entry', onclick: () => { state.subPage = to; renderSub(); } },
    el('span', { class: 'name' }, name));
}

export function showAppPage() {
  const at = pages(state.apps).findIndex((page) => page.some((a) => a.name === state.app));
  state.subPage = at < 0 ? 0 : at;
}

export function renderSub() {
  const sub = $('#sub');
  sub.hidden = !kind();
  if (!kind()) return;
  const all = pages(state.apps);
  const at = Math.min(state.subPage, all.length - 1);
  const total = state.apps.reduce((sum, a) => sum + a.count, 0);
  const first = at === 0 ? link('All', total, address(state.menu), state.app === null) : step('‹ Back', at - 1);
  const apps = all[at].map((a) => link(a.name || 'No app', a.count, address(state.menu, a.name), a.name === state.app));
  const more = at < all.length - 1 ? step('More ›', at + 1) : null;
  sub.replaceChildren(first, ...apps, ...(more ? [more] : []));
}
