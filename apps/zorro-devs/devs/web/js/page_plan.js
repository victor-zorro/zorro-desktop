// The Plan page: the existing plan page, shown inside DEVS.
import { $ } from './dom.js';

export function renderPlan() {
  const frame = $('#page-plan');
  if (!frame.getAttribute('src')) frame.setAttribute('src', 'plan/');
}
