// Small helpers: build elements, talk to the laptop, say what happened.
export const $ = (selector) => document.querySelector(selector);

export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(props)) {
    if (name === 'class') node.className = value;
    else if (name.startsWith('on')) node.addEventListener(name.slice(2), value);
    else if (value !== null && value !== undefined) node.setAttribute(name, value);
  }
  node.append(...children.filter((child) => child !== null && child !== undefined));
  return node;
}

export function say(text, bad = false) {
  const line = $('#say');
  line.textContent = text;
  line.className = 'saved ' + (bad ? 'err' : 'ok');
}

async function answer(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || 'error ' + response.status);
  return data;
}

export async function get(path) {
  return answer(await fetch(path, { cache: 'no-store' }));
}

export async function post(path, body) {
  return answer(await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body) }));
}

// Run a change; the line at the bottom says what happened.
export async function apply(change, done) {
  try {
    const result = await change();
    say(done);
    return result;
  } catch (error) {
    say('Not saved: ' + error.message, true);
    return null;
  }
}
