// zorro greeter — login logic (nody-greeter / web-greeter lightdm API).
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const login = $('login'), entry = $('entry'), msg = $('msg'), userEl = $('user');
  let ready = false, user = null, appeared = false;

  // ---- glitch sync: CSS jitter while the shader glitches ----------------
  let burstTimer;
  FX.onBurst((strength, ms) => {
    if (strength < .3) return;
    document.body.classList.add('burst');
    clearTimeout(burstTimer);
    burstTimer = setTimeout(() => document.body.classList.remove('burst'), ms);
  });

  // ---- clock ---------------------------------------------------------------
  function tick() {
    const d = new Date();
    const t = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
    $('time').textContent = t; $('time').dataset.text = t;
    $('date').textContent = d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' });
  }
  tick(); setInterval(tick, 1000);

  function setUser(name) {
    userEl.textContent = name || '';
    userEl.dataset.text = name || '';
  }

  function say(text, error) {
    msg.textContent = text || '';
    msg.className = error ? 'error' : '';
  }

  // Show the UI once the startup animation has settled.
  function appear() {
    if (appeared) return;
    appeared = true;
    const wait = Math.max(0, 3300 - (performance.now() - FX.startedAt));
    setTimeout(() => {
      for (const el of [login, $('clock'), $('power')]) {
        el.classList.remove('hidden'); el.classList.add('appear');
        // drop it afterwards, or every glitch (which swaps the animation) replays the fade-in
        el.addEventListener('animationend', (e) => {
          if (e.animationName === 'appear') el.classList.remove('appear');
        });
      }
      FX.burst(.6, 250);
      entry.focus();
    }, wait);
  }

  // ---- lightdm callbacks ---------------------------------------------------
  function showPrompt(text, type) {
    entry.value = '';
    const secret = type === 1 || type === 'password';
    entry.type = secret ? 'password' : 'text';
    entry.placeholder = secret ? 'password' : (text || 'login').replace(/:\s*$/, '');
    entry.focus();
  }

  function showMessage(text, type) {
    if (!text) return;
    say(text, type === 1 || type === 'error');
  }

  function authComplete() {
    const L = window.lightdm;
    if (L.is_authenticated) {
      say('');
      const ses = (L.sessions || []).find((s) => s.key === 'openbox');
      const key = ses ? ses.key : L.default_session;
      document.body.classList.add('leaving');
      FX.powerOff(() => L.start_session(key));
    } else {
      say('access denied', true);
      FX.burst(1, 600);
      login.classList.remove('shake'); void login.offsetWidth; login.classList.add('shake');
      setTimeout(start, 900);
    }
  }

  function start() {
    const L = window.lightdm;
    const users = L.users || [];
    user = users.length === 1 ? users[0] : null;
    $('host').textContent = (L.hostname || 'signal');
    setUser(user ? (user.display_name || user.username) : '');
    if (L.in_authentication) L.cancel_authentication();
    L.authenticate(user ? user.username : null);
  }

  entry.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') return;
    if (e.key === 'Escape') { entry.value = ''; return; }
    if (Math.random() < .25) FX.burst(.2, 50);   // tiny flicker while typing
  });

  $('form').addEventListener('submit', (e) => {
    e.preventDefault();
    const L = window.lightdm;
    if (!L) return;
    if (!L.in_authentication) { start(); return; }
    if (!user && entry.type === 'text') setUser(entry.value);
    say('');
    L.respond(entry.value);
    entry.value = '';
  });

  document.addEventListener('mousedown', (e) => {
    if (!e.target.closest('button')) setTimeout(() => entry.focus(), 0);
  });

  $('power').addEventListener('click', (e) => {
    const b = e.target.closest('button');
    const L = window.lightdm;
    if (!b || !L) return;
    const act = b.dataset.act;
    FX.burst(.9, 300);
    setTimeout(() => {
      if (act === 'suspend') L.suspend();
      else if (act === 'restart') L.restart();
      else if (act === 'shutdown') L.shutdown();
    }, 250);
  });

  function onReady() {
    if (ready) return;
    ready = true;
    const L = window.lightdm;
    L.show_prompt.connect(showPrompt);
    L.show_message.connect(showMessage);
    L.authentication_complete.connect(authComplete);
    for (const [act, can] of [['suspend', L.can_suspend], ['restart', L.can_restart], ['shutdown', L.can_shutdown]])
      if (can === false) document.querySelector(`[data-act="${act}"]`).disabled = true;
    start();
    appear();
  }

  window.addEventListener('GreeterReady', onReady);

  // Outside the greeter (browser preview) load a fake lightdm.
  setTimeout(() => {
    if (ready) return;
    if (window.lightdm && window.lightdm.authenticate) { onReady(); return; }
    const s = document.createElement('script');
    s.src = 'dev/mock.js';
    s.onload = onReady;
    s.onerror = () => { appear(); say('no greeter backend', true); };
    document.body.appendChild(s);
  }, 1200);
})();
