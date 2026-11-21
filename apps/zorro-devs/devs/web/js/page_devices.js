// The Devices page: every device with its counts, and the automatic checks.
import { $, apply, el, get, post, say } from './dom.js';

const COUNTS = ['ok', 'fail', 'untested', 'stale'];

function number(value) {
  return el('span', { class: 'num' + (value ? '' : ' zero') }, String(value));
}

function deviceRow(device) {
  return el('div', { class: 'row device' },
    el('span', { class: 'cut' }, device.name, device.this ? el('span', { class: 'chip this' }, 'this device') : null),
    ...COUNTS.map((name) => number(device[name])));
}

function checkRow(name, result) {
  const sign = !result ? el('span', { class: 'mark untested' }, '○')
    : el('span', { class: 'mark ' + (result.ok ? 'ok' : 'fail') }, result.ok ? '✓' : '✕');
  return el('div', { class: 'row check' }, el('span', { class: 'num' }, name), sign,
    el('span', { class: 'cut cat', title: result ? result.detail : '' }, result ? result.detail : 'not run yet'),
    el('span', { class: 'cut cat at' }, result ? result.at.replace('T', ' ') : ''));
}

export async function renderDevices() {
  let data;
  try {
    data = await get('api/devices');
  } catch (error) {
    return say('The laptop does not answer.', true);
  }
  const head = el('div', { class: 'row device head label' }, el('span', {}, 'Device'),
    ...COUNTS.map((name) => el('span', {}, name)));
  $('#device-list').replaceChildren(head, ...data.devices.map(deviceRow));
  $('#check-list').replaceChildren(...data.names.map((name) => checkRow(name, data.checks[name])));
}

async function runChecks(button) {
  button.disabled = true;
  say('Running the checks…');
  const done = await apply(() => post('api/check', {}), 'Checks done.');
  if (done) {
    const failed = Object.values(done.checks).filter((c) => !c.ok).length;
    say(failed ? `Checks done: ${failed} failed.` : 'Checks done: all ok.', failed > 0);
  }
  button.disabled = false;
  renderDevices();
}

export function setUpDevices() {
  $('#run-checks').addEventListener('click', (event) => runChecks(event.currentTarget));
}
