// Start: follow the address, show the right page, and look again every 5 seconds.
import { $, get, say } from './dom.js';
import { renderMenu, renderSub, showAppPage } from './menu.js';
import { renderDevices, setUpDevices } from './page_devices.js';
import { renderItems, setUpItems } from './page_items.js';
import { renderPlan } from './page_plan.js';
import { renderPanel, setUpPanel } from './panel.js';
import { entry, kind, readAddress, state } from './state.js';

const EVERY = 5000;
let timer = null;

async function loadItems() {
  const app = state.app === null ? '' : '&app=' + encodeURIComponent(state.app);
  const list = await get(`api/items?kind=${kind()}${app}`);
  Object.assign(state, { items: list.items, devices: list.devices, here: list.this });
}

async function loadCounts() {
  const apps = await get('api/apps?kind=' + (kind() || ''));
  Object.assign(state, { apps: apps.apps, kinds: apps.kinds });
}

async function refresh() {
  try {
    const asked = location.hash;
    await Promise.all([loadCounts(), kind() ? loadItems() : null]);
    if (asked !== location.hash) return;
    renderMenu(); renderSub();
    if (kind()) { renderItems(); renderPanel(); }
    if (state.menu === 'devices') await renderDevices();
  } catch (error) {
    say('The laptop does not answer.', true);
  }
}

async function show() {
  readAddress();
  const app = state.app === null ? '' : ' · ' + (state.app || 'No app');
  $('#title').textContent = entry().name + (kind() ? app : '');
  $('#page-items').hidden = !kind();
  $('#page-devices').hidden = state.menu !== 'devices';
  $('#page-plan').hidden = state.menu !== 'plan';
  if (!kind()) state.open = null;
  renderMenu(); renderSub(); renderPanel();
  if (state.menu === 'plan') renderPlan();
  await refresh();
  if (kind() && state.app !== null) { showAppPage(); renderSub(); }
}

function live() {
  clearInterval(timer);
  timer = document.hidden ? null : setInterval(refresh, EVERY);
}

setUpItems(refresh);
setUpPanel(refresh);
setUpDevices();
window.addEventListener('hashchange', show);
document.addEventListener('visibilitychange', () => { live(); if (!document.hidden) refresh(); });
show();
live();
