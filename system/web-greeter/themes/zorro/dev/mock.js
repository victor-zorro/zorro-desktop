// Fake lightdm for previewing the theme in a normal browser.
// Never loaded inside the real greeter. Password "test" succeeds.
(() => {
  const sig = () => { const fns = []; return { connect: (f) => fns.push(f), emit: (...a) => fns.forEach((f) => f(...a)) }; };
  const L = {
    hostname: 'preview', users: [{ username: 'zorro', display_name: 'zorro' }],
    sessions: [{ key: 'openbox', name: 'Openbox' }], default_session: 'openbox',
    can_suspend: true, can_restart: true, can_shutdown: true,
    in_authentication: false, is_authenticated: false,
    show_prompt: sig(), show_message: sig(), authentication_complete: sig(),
    authenticate(u) { this.in_authentication = true; setTimeout(() => this.show_prompt.emit(u ? 'Password:' : 'login:', u ? 1 : 0), 50); },
    cancel_authentication() { this.in_authentication = false; },
    respond(v) {
      this.in_authentication = false;
      this.is_authenticated = v === 'test';
      setTimeout(() => this.authentication_complete.emit(), 400);
    },
    start_session(k) { document.title = 'started ' + k; setTimeout(() => location.reload(), 1500); },
    suspend() { console.log('suspend'); }, restart() { console.log('restart'); }, shutdown() { console.log('shutdown'); },
  };
  window.lightdm = L;
})();
