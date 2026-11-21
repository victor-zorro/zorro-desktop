// Where you are (menu, app, open item) lives in the address: #features/Dialer/item-id
export const MENU = [
  { id: 'plan', name: 'Plan' },
  { id: 'features', name: 'Features', kind: 'feature' },
  { id: 'bugs', name: 'Bugs', kind: 'bug' },
  { id: 'wishes', name: 'Wishes', kind: 'wish' },
  { id: 'backlog', name: 'Backlog', kind: 'backlog' },
  { id: 'decisions', name: 'Decisions', kind: 'decision' },
  { id: 'devices', name: 'Devices' },
];
const ALL = '*', NO_APP = '-';

export const state = {
  menu: 'features', app: null, open: null,     // app: null = all, '' = items without an app
  subPage: 0, search: '', onlyHere: false, onlyStale: false,
  items: [], devices: [], here: '', apps: [], kinds: {},
};

export const entry = () => MENU.find((m) => m.id === state.menu);
export const kind = () => entry().kind;

export function address(menu, app = null, open = null) {
  const token = app === null ? ALL : app === '' ? NO_APP : encodeURIComponent(app);
  let hash = '#' + menu;
  if (app !== null || open) hash += '/' + token;
  if (open) hash += '/' + open;
  return hash;
}

export function readAddress() {
  const [menu, token, open] = location.hash.slice(1).split('/');
  const old = state.menu;
  state.menu = MENU.some((m) => m.id === menu) ? menu : 'features';
  if (!token || token === ALL) state.app = null;
  else state.app = token === NO_APP ? '' : decodeURIComponent(token);
  state.open = /^[a-z0-9][a-z0-9-]{0,79}$/.test(open || '') ? open : null;
  if (old !== state.menu) state.subPage = 0;
}
