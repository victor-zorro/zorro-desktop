// The Plan page: the build plan (its own small server on port 8099: progress, design chat),
// shown inside DEVS.
import { $ } from './dom.js';

export function renderPlan() {
  const frame = $('#page-plan');
  if (!frame.getAttribute('src')) frame.setAttribute('src', `${location.protocol}//${location.hostname}:8099/`);
}
